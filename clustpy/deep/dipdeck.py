"""
@authors:
Collin Leiber
"""

from scipy.spatial.distance import cdist
import numpy as np
from clustpy.utils import dip_test, dip_pval
import torch
from clustpy.deep._utils import detect_device, encode_batchwise, squared_euclidean_distance, int_to_one_hot, \
    set_torch_seed, run_initial_clustering, embedded_kmeans_prediction
from clustpy.deep._data_utils import get_dataloader, augmentation_invariance_check
from clustpy.deep._train_utils import get_trained_autoencoder
from sklearn.cluster import KMeans
from sklearn.base import BaseEstimator, ClusterMixin
from sklearn.utils import check_random_state


def _dip_deck(X: np.ndarray, n_clusters_init: int, dip_merge_threshold: float, cluster_loss_weight: float,
              max_n_clusters: int, min_n_clusters: int, batch_size: int,
              pretrain_optimizer_params: dict, clustering_optimizer_params: dict, pretrain_epochs: int,
              clustering_epochs: int, optimizer_class: torch.optim.Optimizer,
              loss_fn: torch.nn.modules.loss._Loss, autoencoder: torch.nn.Module, embedding_size: int,
              max_cluster_size_diff_factor: float, pval_strategy: str, n_boots: int, custom_dataloaders: tuple,
              augmentation_invariance: bool, initial_clustering_class: ClusterMixin, initial_clustering_params: dict,
              random_state: np.random.RandomState, debug: bool) -> (np.ndarray, int, np.ndarray, torch.nn.Module):
    """
    Start the actual DipDECK clustering procedure on the input data set.

    Parameters
    ----------
    X : np.ndarray / torch.Tensor
        the given data set. Can be a np.ndarray or a torch.Tensor
    n_clusters_init : int
        initial number of clusters. Can be None if a corresponding initial_clustering_class is given, e.g. DBSCAN
    dip_merge_threshold : float
        threshold regarding the Dip-p-value that defines if two clusters should be merged. Must be bvetween 0 and 1
    cluster_loss_weight : float
        weight of the clustering loss compared to the reconstruction loss
    max_n_clusters : int
        maximum number of clusters. Must be larger than min_n_clusters. If the result has more clusters, a merge will be forced
    min_n_clusters : int
        minimum number of clusters. Must be larger than 0, smaller than max_n_clusters and smaller than n_clusters_init.
        When this number of clusters is reached, all further merge processes will be hindered
    batch_size : int
        size of the data batches
    pretrain_optimizer_params : dict
        parameters of the optimizer for the pretraining of the autoencoder, includes the learning rate
    clustering_optimizer_params : dict
        parameters of the optimizer for the actual clustering procedure, includes the learning rate
    pretrain_epochs : int
        number of epochs for the pretraining of the autoencoder
    clustering_epochs : int
        number of epochs for the actual clustering procedure. Will reset after each merge
    optimizer_class : torch.optim.Optimizer
        the optimizer class
    loss_fn : torch.nn.modules.loss._Loss
        loss function for the reconstruction
    autoencoder : torch.nn.Module
        the input autoencoder. If None a new FeedforwardAutoencoder will be created
    embedding_size : int
        size of the embedding within the autoencoder
    max_cluster_size_diff_factor : float
        The maximum different in size when comparing two clusters regarding the number of samples.
        If one cluster surpasses this difference factor, only the max_cluster_size_diff_factor*(size of smaller cluster) closest samples will be used for the Dip calculation
    pval_strategy : str
        Defines which strategy to use to receive dip-p-vales. Possibilities are 'table', 'function' and 'bootstrap'
    n_boots : int
        Number of bootstraps used to calculate dip-p-values. Only necessary if pval_strategy is 'bootstrap'
    custom_dataloaders : tuple
        tuple consisting of a trainloader (random order) at the first and a test loader (non-random order) at the second position.
        If None, the default dataloaders will be used
    augmentation_invariance : bool
        If True, augmented samples provided in custom_dataloaders[0] will be used to learn
        cluster assignments that are invariant to the augmentation transformations
    initial_clustering_class : ClusterMixin
        clustering class to obtain the initial cluster labels after the pretraining
    initial_clustering_params : dict
        parameters for the initial clustering class
    random_state : np.random.RandomState
        use a fixed random state to get a repeatable solution
    debug : bool
        If true, additional information will be printed to the console

    Returns
    -------
    tuple : (np.ndarray, int, np.ndarray, torch.nn.Module)
        The labels as identified by DipDECK,
        The final number of clusters,
        The cluster centers as identified by DipDECK,
        The final autoencoder
    """
    if max_n_clusters < min_n_clusters:
        raise Exception("max_n_clusters can not be smaller than min_n_clusters")
    if min_n_clusters <= 0:
        raise Exception("min_n_clusters must be greater than zero")
    if n_clusters_init < min_n_clusters and n_clusters_init is not None:
        raise Exception("n_clusters can not be smaller than min_n_clusters")
    if dip_merge_threshold < 0 or dip_merge_threshold > 1:
        raise Exception("dip_merge_threshold must be between 0 and 1")
    device = detect_device()
    if custom_dataloaders is None:
        trainloader = get_dataloader(X, batch_size, True, False)
        testloader = get_dataloader(X, batch_size, False, False)
    else:
        trainloader, testloader = custom_dataloaders
        # Get new X from dataloader (important if transformations are used within the dataloader)
        X_new = []
        for batch in testloader:
            X_new.append(batch[1].detach().cpu())
        X = torch.cat(X_new, dim=0).numpy()
    autoencoder = get_trained_autoencoder(trainloader, pretrain_optimizer_params, pretrain_epochs, device,
                                          optimizer_class, loss_fn, embedding_size, autoencoder)
    # Execute initial clustering in embedded space
    embedded_data = encode_batchwise(testloader, autoencoder, device)
    n_clusters_init, cluster_labels_cpu, init_centers, _ = run_initial_clustering(embedded_data, n_clusters_init,
                                                                                  initial_clustering_class,
                                                                                  initial_clustering_params,
                                                                                  random_state)
    # Get nearest points to optimal centers
    centers_cpu, embedded_centers_cpu = _get_nearest_points_to_optimal_centers(X, init_centers, embedded_data)
    # Initial dip values
    dip_matrix_cpu = _get_dip_matrix(embedded_data, embedded_centers_cpu, cluster_labels_cpu, n_clusters_init,
                                     max_cluster_size_diff_factor, pval_strategy, n_boots, random_state)
    # Use DipDECK optimizer parameters (usually learning rate is reduced by a magnitude of 10)
    optimizer = optimizer_class(autoencoder.parameters(), **clustering_optimizer_params)
    # Start training
    cluster_labels_cpu, n_clusters_current, centers_cpu, autoencoder = _dip_deck_training(X, n_clusters_init,
                                                                                          dip_merge_threshold,
                                                                                          cluster_loss_weight,
                                                                                          centers_cpu,
                                                                                          cluster_labels_cpu,
                                                                                          dip_matrix_cpu,
                                                                                          max_n_clusters,
                                                                                          min_n_clusters,
                                                                                          clustering_epochs,
                                                                                          optimizer, loss_fn,
                                                                                          autoencoder,
                                                                                          device, trainloader,
                                                                                          testloader,
                                                                                          augmentation_invariance,
                                                                                          max_cluster_size_diff_factor,
                                                                                          pval_strategy, n_boots,
                                                                                          random_state, debug)
    # Return results
    return cluster_labels_cpu, n_clusters_current, centers_cpu, autoencoder


def _dip_deck_training(X: np.ndarray, n_clusters_current: int, dip_merge_threshold: float, cluster_loss_weight: float,
                       centers_cpu: np.ndarray, cluster_labels_cpu: np.ndarray,
                       dip_matrix_cpu: np.ndarray, max_n_clusters: int, min_n_clusters: int, clustering_epochs: int,
                       optimizer: torch.optim.Optimizer, loss_fn: torch.nn.modules.loss._Loss,
                       autoencoder: torch.nn.Module, device: torch.device, trainloader: torch.utils.data.DataLoader,
                       testloader: torch.utils.data.DataLoader, augmentation_invariance: bool,
                       max_cluster_size_diff_factor: float, pval_strategy: str, n_boots: int,
                       random_state: np.random.RandomState, debug: bool) -> (
        np.ndarray, int, np.ndarray, torch.nn.Module):
    """
    The training function of DipDECK. Contains most of the essential functionalities.

    Parameters
    ----------
    X : np.ndarray / torch.Tensor
        the given data set. Can be a np.ndarray or a torch.Tensor
    n_clusters_current : int
        current number of clusters. Is equal to n_clusters_init in the beginning
    dip_merge_threshold : float
        threshold regarding the Dip-p-value that defines if two clusters should be merged. Must be bvetween 0 and 1
    cluster_loss_weight : float
        weight of the clustering loss compared to the reconstruction loss
    centers_cpu : np.ndarray
        The current cluster centers, saved as numpy array (not torch.Tensor)
        Equals the result of the initial KMeans clusters in the beginning.
    cluster_labels_cpu : np.ndarray
        The current cluster labels, saved as numpy array (not torch.Tensor)
        Equals the result of the initial KMeans labels in the beginning.
    dip_matrix_cpu : np.ndarray
        The current dip matrix, saved as numpy array (not torch.Tensor).
        Symmetric matrix containing the Dip-values between each pair of clusters.
    max_n_clusters : int
        maximum number of clusters. Must be larger than min_n_clusters. If the result has more clusters, a merge will be forced
    min_n_clusters : int
        minimum number of clusters. Must be larger than 0, smaller than max_n_clusters and smaller than n_clusters_init.
        When this number of clusters is reached, all further merge processes will be hindered
    clustering_epochs : int
        number of epochs for the actual clustering procedure
    optimizer : torch.optim.Optimizer
        the optimizer object
    loss_fn : torch.nn.modules.loss._Loss
        loss function for the reconstruction
    autoencoder : torch.nn.Module
        the input autoencoder
    device : torch.device
        device to be trained on
    trainloader : torch.utils.data.DataLoader
        dataloader to be used for training
    testloader : torch.utils.data.DataLoader
        dataloader to be used for update of the labels, centers and the dip matrix
    augmentation_invariance : bool
        If True, augmented samples provided in custom_dataloaders[0] will be used to learn
        cluster assignments that are invariant to the augmentation transformations
    max_cluster_size_diff_factor : float
        The maximum different in size when comparing two clusters regarding the number of samples.
        If one cluster surpasses this difference factor, only the max_cluster_size_diff_factor*(size of smaller cluster) closest samples will be used for the Dip calculation
    pval_strategy : str
        Defines which strategy to use to receive dip-p-vales. Possibilities are 'table', 'function' and 'bootstrap'
    n_boots : int
        Number of bootstraps used to calculate dip-p-values. Only necessary if pval_strategy is 'bootstrap'
    random_state : np.random.RandomState
        use a fixed random state to get a repeatable solution
    debug : bool
        If true, additional information will be printed to the console

    Returns
    -------
    tuple : (np.ndarray, int, np.ndarray, torch.nn.Module)
        The labels as identified by DipDECK,
        The final number of clusters,
        The cluster centers as identified by DipDECK,
        The final autoencoder
    """
    i = 0
    while i < clustering_epochs:
        cluster_labels_torch = torch.from_numpy(cluster_labels_cpu).int().to(device)
        centers_torch = torch.from_numpy(centers_cpu).float().to(device)
        dip_matrix_torch = torch.from_numpy(dip_matrix_cpu).float().to(device)
        # Get dip costs matrix
        dip_matrix_eye = dip_matrix_torch + torch.eye(n_clusters_current, device=device)
        dip_matrix_final = dip_matrix_eye / dip_matrix_eye.sum(1).reshape((-1, 1))
        # Iterate over batches
        for batch in trainloader:
            ids = batch[0]
            # Reconstruction Loss
            if augmentation_invariance:
                ae_loss, embedded, _ = autoencoder.loss([batch[0], batch[2]], loss_fn, device)
                ae_loss_aug, embedded_aug, _ = autoencoder.loss([batch[0], batch[1]], loss_fn, device)
                ae_loss = (ae_loss + ae_loss_aug) / 2
            else:
                ae_loss, embedded, _ = autoencoder.loss(batch, loss_fn, device)
            # Encode centers
            embedded_centers_torch = autoencoder.encode(centers_torch)
            # Get distances between points and centers. Get nearest center
            squared_diffs = squared_euclidean_distance(embedded, embedded_centers_torch)
            # Update labels? Pause is needed, so cluster labels can adjust to the new structure
            if i != 0:
                # Update labels
                current_labels = squared_diffs.argmin(1)
                # cluster_labels_torch[ids] = current_labels
            else:
                current_labels = cluster_labels_torch[ids]
            onehot_labels = int_to_one_hot(current_labels, n_clusters_current).float()
            cluster_relationships = torch.matmul(onehot_labels, dip_matrix_final)
            escaped_diffs = cluster_relationships * squared_diffs
            # Normalize loss by cluster distances
            squared_center_diffs = squared_euclidean_distance(embedded_centers_torch, embedded_centers_torch)
            # Ignore zero values (diagonal)
            mask = torch.where(squared_center_diffs != 0)
            masked_center_diffs = squared_center_diffs[mask[0], mask[1]]
            sqrt_masked_center_diffs = masked_center_diffs.sqrt()
            masked_center_diffs_std = sqrt_masked_center_diffs.std() if len(sqrt_masked_center_diffs) > 2 else 0
            # Loss function
            cluster_loss = escaped_diffs.sum(1).mean() * (
                    1 + masked_center_diffs_std) / sqrt_masked_center_diffs.mean()
            if augmentation_invariance:
                # Augmendet cluster loss
                squared_diffs_aug = squared_euclidean_distance(embedded_aug, embedded_centers_torch)
                escaped_diffs_aug = cluster_relationships * squared_diffs_aug
                cluster_loss_aug = escaped_diffs_aug.sum(1).mean() * (
                        1 + masked_center_diffs_std) / sqrt_masked_center_diffs.mean()
                cluster_loss = (cluster_loss + cluster_loss_aug) / 2
            cluster_loss *= cluster_loss_weight
            loss = ae_loss + cluster_loss
            # Backward pass
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
        # Update centers
        embedded_data = encode_batchwise(testloader, autoencoder, device)
        embedded_centers_cpu = autoencoder.encode(centers_torch).detach().cpu().numpy()
        cluster_labels_cpu = np.argmin(cdist(embedded_centers_cpu, embedded_data), axis=0).astype(np.int32)
        optimal_centers = np.array([np.mean(embedded_data[cluster_labels_cpu == cluster_id], axis=0) for cluster_id in
                                    range(n_clusters_current)])
        centers_cpu, embedded_centers_cpu = _get_nearest_points_to_optimal_centers(X, optimal_centers, embedded_data)
        # Update Dips
        dip_matrix_cpu = _get_dip_matrix(embedded_data, embedded_centers_cpu, cluster_labels_cpu, n_clusters_current,
                                         max_cluster_size_diff_factor, pval_strategy, n_boots, random_state)

        if debug:
            print(
                "Iteration {0}  (n_clusters = {4}) - reconstruction loss: {1} / cluster loss: {2} / total loss: {3}".format(
                    i, ae_loss.item(), cluster_loss.item(), loss.item(), n_clusters_current))
            print("max dip", np.max(dip_matrix_cpu), " at ",
                  np.unravel_index(np.argmax(dip_matrix_cpu, axis=None), dip_matrix_cpu.shape))
        # i is increased here. Else next iteration will start with i = 1 instead of 0 after a merge
        i += 1
        # Start merging procedure
        dip_argmax = np.unravel_index(np.argmax(dip_matrix_cpu, axis=None), dip_matrix_cpu.shape)
        # Is merge possible?
        while dip_matrix_cpu[dip_argmax] >= dip_merge_threshold and n_clusters_current > min_n_clusters:
            if debug:
                print("Start merging in iteration {0}.\nMerging clusters {1} with dip value {2}.".format(i,
                                                                                                         dip_argmax,
                                                                                                         dip_matrix_cpu[
                                                                                                             dip_argmax]))
            # Reset iteration and reduce number of cluster
            i = 0
            n_clusters_current -= 1
            cluster_labels_cpu, centers_cpu, embedded_centers_cpu, dip_matrix_cpu = \
                _merge_by_dip_value(X, embedded_data, cluster_labels_cpu, dip_argmax, n_clusters_current, centers_cpu,
                                    embedded_centers_cpu, max_cluster_size_diff_factor, pval_strategy, n_boots,
                                    random_state)
            dip_argmax = np.unravel_index(np.argmax(dip_matrix_cpu, axis=None), dip_matrix_cpu.shape)
        # Optional: Force merging of clusters
        if i == clustering_epochs and n_clusters_current > max_n_clusters:
            # Get smallest cluster
            _, cluster_sizes = np.unique(cluster_labels_cpu, return_counts=True)
            smallest_cluster_id = np.argmin(cluster_sizes)
            smallest_cluster_size = cluster_sizes[smallest_cluster_id]
            i = 0
            n_clusters_current -= 1
            # Is smallest cluster small enough for deletion?
            if smallest_cluster_size < 0.2 * np.mean(cluster_sizes):
                if debug:
                    print(
                        "Remove smallest cluster {0} with size {1}".format(smallest_cluster_id, smallest_cluster_size))
                distances_to_clusters = cdist(embedded_centers_cpu,
                                              embedded_data[cluster_labels_cpu == smallest_cluster_id])
                # Set dist to center which is being removed to inf
                distances_to_clusters[smallest_cluster_id, :] = np.inf
                cluster_labels_cpu[cluster_labels_cpu == smallest_cluster_id] = np.argmin(distances_to_clusters, axis=0)
                cluster_labels_cpu[cluster_labels_cpu >= smallest_cluster_id] -= 1
                optimal_centers = np.array(
                    [np.mean(embedded_data[cluster_labels_cpu == cluster_id], axis=0) for cluster_id in
                     range(n_clusters_current)])
                centers_cpu, embedded_centers_cpu = _get_nearest_points_to_optimal_centers(X, optimal_centers,
                                                                                           embedded_data)
                # Update dip values
                dip_matrix_cpu = _get_dip_matrix(embedded_data, embedded_centers_cpu, cluster_labels_cpu,
                                                 n_clusters_current, max_cluster_size_diff_factor, pval_strategy,
                                                 n_boots, random_state)
            else:
                # Else: merge clusters with hightest dip
                if debug:
                    print("Force merge of clusters {0} with dip value {1}".format(dip_argmax,
                                                                                  dip_matrix_cpu[dip_argmax]))

                cluster_labels_cpu, centers_cpu, _, dip_matrix_cpu = \
                    _merge_by_dip_value(X, embedded_data, cluster_labels_cpu, dip_argmax, n_clusters_current,
                                        centers_cpu, embedded_centers_cpu, max_cluster_size_diff_factor, pval_strategy,
                                        n_boots, random_state)
        if n_clusters_current == 1:
            if debug:
                print("Only one cluster left")
            break
    return cluster_labels_cpu, n_clusters_current, centers_cpu, autoencoder


def _merge_by_dip_value(X: np.ndarray, embedded_data: np.ndarray, cluster_labels_cpu: np.ndarray,
                        dip_argmax: np.ndarray, n_clusters_current: int, centers_cpu: np.ndarray,
                        embedded_centers_cpu: np.ndarray, max_cluster_size_diff_factor: float, pval_strategy: str,
                        n_boots: int, random_state: np.random.RandomState) -> (
        np.ndarray, np.ndarray, np.ndarray, np.ndarray):
    """
    Merge the clusters within dip_argmax because their Dip-value is larger than the threshold.
    Sets the labels of the two cluster to n_clusters - 1. The other labels are adjusted accordingly.
    Further, the centers, embedded centers and the dip matrix will be updated according to the new structure.

    Parameters
    ----------
    X : np.ndarray
        the given data set
    embedded_data : np.ndarray
        the embedded data set
    cluster_labels_cpu : np.ndarray
        The current cluster labels, saved as numpy array (not torch.Tensor)
    dip_argmax : np.ndarray
        The indices of the two clusters having the largest Dip-value within the dip matrix
    n_clusters_current : int
        current number of clusters. Is equal to n_clusters_init in the beginning
    centers_cpu : np.ndarray
        The current cluster centers, saved as numpy array (not torch.Tensor)
    embedded_centers_cpu : np.ndarray
        The embedded cluster centers, saved as numpy array (not torch.Tensor)
    max_cluster_size_diff_factor : float
        The maximum different in size when comparing two clusters regarding the number of samples.
        If one cluster surpasses this difference factor, only the max_cluster_size_diff_factor*(size of smaller cluster) closest samples will be used for the Dip calculation
    pval_strategy : str
        Defines which strategy to use to receive dip-p-vales. Possibilities are 'table', 'function' and 'bootstrap'
    n_boots : int
        Number of bootstraps used to calculate dip-p-values. Only necessary if pval_strategy is 'bootstrap'
    random_state : np.random.RandomState
        use a fixed random state to get a repeatable solution

    Returns
    -------
    tuple : (np.ndarray, np.ndarray, np.ndarray, np.ndarray)
        The updated labels
        The updated centers,
        The updated embedded centers,
        The updated dip matrix
    """
    # Get points in clusters
    points_in_center_1 = len(cluster_labels_cpu[cluster_labels_cpu == dip_argmax[0]])
    points_in_center_2 = len(cluster_labels_cpu[cluster_labels_cpu == dip_argmax[1]])
    # update labels
    for j, l in enumerate(cluster_labels_cpu):
        if l == dip_argmax[0] or l == dip_argmax[1]:
            cluster_labels_cpu[j] = n_clusters_current - 1
        elif l < dip_argmax[0] and l < dip_argmax[1]:
            cluster_labels_cpu[j] = l
        elif l > dip_argmax[0] and l > dip_argmax[1]:
            cluster_labels_cpu[j] = l - 2
        else:
            cluster_labels_cpu[j] = l - 1
    # Find new center position
    optimal_new_center = (embedded_centers_cpu[dip_argmax[0]] * points_in_center_1 +
                          embedded_centers_cpu[dip_argmax[1]] * points_in_center_2) / (
                                 points_in_center_1 + points_in_center_2)
    new_center_cpu, new_embedded_center_cpu = _get_nearest_points_to_optimal_centers(X, [optimal_new_center],
                                                                                     embedded_data)
    # Remove the two old centers and add the new one
    centers_cpu_tmp = np.delete(centers_cpu, dip_argmax, axis=0)
    centers_cpu = np.append(centers_cpu_tmp, new_center_cpu, axis=0)
    embedded_centers_cpu_tmp = np.delete(embedded_centers_cpu, dip_argmax, axis=0)
    embedded_centers_cpu = np.append(embedded_centers_cpu_tmp, new_embedded_center_cpu, axis=0)
    # Update dip values
    dip_matrix_cpu = _get_dip_matrix(embedded_data, embedded_centers_cpu, cluster_labels_cpu,
                                     n_clusters_current, max_cluster_size_diff_factor, pval_strategy, n_boots,
                                     random_state)
    return cluster_labels_cpu, centers_cpu, embedded_centers_cpu, dip_matrix_cpu


def _get_nearest_points_to_optimal_centers(X: np.ndarray, optimal_centers: np.ndarray, embedded_data: np.ndarray) -> (
        np.ndarray, np.ndarray):
    """
    Get the nearest embedded points within the dataset to a set of optimal centers.
    Additionally, this method will return the corresponding point in the full dimensional space.

    Parameters
    ----------
    X : np.ndarray
        the given data set
    optimal_centers : np.ndarray
        the set of optimal centers
    embedded_data : np.ndarray
        the embedded data set

    Returns
    -------
    tuple : (np.ndarray, np.ndarray)
        The closest points as new centers in the full space,
        The closest points as new centers in the embedded space
    """
    best_center_points = np.argmin(cdist(optimal_centers, embedded_data), axis=1)
    centers_cpu = X[best_center_points, :]
    embedded_centers_cpu = embedded_data[best_center_points, :]
    return centers_cpu, embedded_centers_cpu


def _get_nearest_points(points_in_larger_cluster: np.ndarray, center: np.ndarray, size_smaller_cluster: int,
                        max_cluster_size_diff_factor: float, min_sample_size: int = 50) -> np.ndarray:
    """
    Get a subset of a cluster. The subset should contain those points that are closest to the cluster center of a second, smaller cluster.
    This method is used when difference in size between the larger cluster and the smaller cluster is greater than max_cluster_size_diff_factor.

    Parameters
    ----------
    points_in_larger_cluster : np.ndarray
        The samples within the larger cluster
    center : np.ndarray
        The cluster center of the smaller cluster.
    size_smaller_cluster : int
        The size of the smaller cluster
    max_cluster_size_diff_factor : float
        The maximum different in size when comparing two clusters regarding the number of samples.
        In the end the larger cluster will only contain the max_cluster_size_diff_factor*(size of smaller cluster) closest samples to the cluster center of the smaller cluster
    min_sample_size : int
        Minimum number of samples that should be considered (equals the combined number of samples) (default: 50)

    Returns
    -------
    subset_all_points: np.ndarray
        the subset of the larger cluster
    """
    distances = cdist(points_in_larger_cluster, [center])
    nearest_points = np.argsort(distances, axis=0)
    # Check if more points should be taken because the other cluster is too small
    sample_size = size_smaller_cluster * max_cluster_size_diff_factor
    if size_smaller_cluster + sample_size < min_sample_size:
        sample_size = min(min_sample_size - size_smaller_cluster, len(points_in_larger_cluster))
    subset_all_points = points_in_larger_cluster[nearest_points[:sample_size, 0]]
    return subset_all_points


def _get_dip_matrix(embedded_data: np.ndarray, embedded_centers_cpu: np.ndarray, cluster_labels_cpu: np.ndarray,
                    n_clusters: int, max_cluster_size_diff_factor: float, pval_strategy: str, n_boots: int,
                    random_state: np.random.RandomState) -> np.ndarray:
    """
    Calculate the dip matrix. Contains the pair-wise Dip-values between all cluster combinations.
    Here, the objects from the two clusters will be projected onto the connection axis between ther cluster centers.

    Parameters
    ----------
    embedded_data : np.ndarray
        the embedded data set
    embedded_centers_cpu : np.ndarray
        The embedded cluster centers, saved as numpy array (not torch.Tensor)
    cluster_labels_cpu : np.ndarray
        The current cluster labels, saved as numpy array (not torch.Tensor)
    n_clusters : int
        The number of clusters
    max_cluster_size_diff_factor : float
        The maximum different in size when comparing two clusters regarding the number of samples.
        If one cluster surpasses this difference factor, only the max_cluster_size_diff_factor*(size of smaller cluster) closest samples will be used for the Dip calculation
    pval_strategy : str
        Defines which strategy to use to receive dip-p-vales. Possibilities are 'table', 'function' and 'bootstrap'
    n_boots : int
        Number of bootstraps used to calculate dip-p-values. Only necessary if pval_strategy is 'bootstrap'
    random_state : np.random.RandomState
        use a fixed random state to get a repeatable solution

    Returns
    -------
    dip_matrix : np.ndarray
        The final dip matrix
    """
    dip_matrix = np.zeros((n_clusters, n_clusters))
    # Loop over all combinations of centers
    for i in range(0, n_clusters - 1):
        for j in range(i + 1, n_clusters):
            center_diff = embedded_centers_cpu[i] - embedded_centers_cpu[j]
            points_in_i = embedded_data[cluster_labels_cpu == i]
            points_in_j = embedded_data[cluster_labels_cpu == j]
            points_in_i_or_j = np.append(points_in_i, points_in_j, axis=0)
            proj_points = np.dot(points_in_i_or_j, center_diff)
            dip_value = dip_test(proj_points)
            dip_p_value = dip_pval(dip_value, proj_points.shape[0], pval_strategy, n_boots, random_state)
            # Check if clusters sizes differ heavily
            if points_in_i.shape[0] > points_in_j.shape[0] * max_cluster_size_diff_factor or \
                    points_in_j.shape[0] > points_in_i.shape[0] * max_cluster_size_diff_factor:
                if points_in_i.shape[0] > points_in_j.shape[0] * max_cluster_size_diff_factor:
                    points_in_i = _get_nearest_points(points_in_i, embedded_centers_cpu[j], points_in_j.shape[0],
                                                      max_cluster_size_diff_factor)
                elif points_in_j.shape[0] > points_in_i.shape[0] * max_cluster_size_diff_factor:
                    points_in_j = _get_nearest_points(points_in_j, embedded_centers_cpu[i], points_in_i.shape[0],
                                                      max_cluster_size_diff_factor)
                points_in_i_or_j = np.append(points_in_i, points_in_j, axis=0)
                proj_points = np.dot(points_in_i_or_j, center_diff)
                dip_value_2 = dip_test(proj_points)
                dip_p_value_2 = dip_pval(dip_value_2, proj_points.shape[0], pval_strategy, n_boots, random_state)
                dip_p_value = min(dip_p_value, dip_p_value_2)
            # Add pval to dip matrix
            dip_matrix[i][j] = dip_p_value
            dip_matrix[j][i] = dip_p_value
    return dip_matrix


class DipDECK(BaseEstimator, ClusterMixin):
    """
    The Deep Embedded Clustering with k-Estimation (DipDECK) algorithm.
    First, an autoencoder (AE) will be trained (will be skipped if input autoencoder is given).
    Afterward, KMeans identifies the initial clusters using an overestimated number of clusters.
    Last, the AE will be optimized using the DipDECK loss function.
    If any Dip-value exceeds the dip_merge_threshold, the corresponding clusters will be merged.

    Parameters
    ----------
    n_clusters_init : int
        initial number of clusters. Can be None if a corresponding initial_clustering_class is given, e.g. DBSCAN (default: 35)
    dip_merge_threshold : float
        threshold regarding the Dip-p-value that defines if two clusters should be merged. Must be bvetween 0 and 1 (default: 0.9)
    cluster_loss_weight : float
        weight of the clustering loss compared to the reconstruction loss (default: 1)
    max_n_clusters : int
        maximum number of clusters. Must be larger than min_n_clusters. If the result has more clusters, a merge will be forced (default: np.inf)
    min_n_clusters : int
        minimum number of clusters. Must be larger than 0, smaller than max_n_clusters and smaller than n_clusters_init.
        When this number of clusters is reached, all further merge processes will be hindered (default: 1)
    batch_size : int
        size of the data batches (default: 256)
    pretrain_optimizer_params : dict
        parameters of the optimizer for the pretraining of the autoencoder, includes the learning rate (default: {"lr": 1e-3})
    clustering_optimizer_params : dict
        parameters of the optimizer for the actual clustering procedure, includes the learning rate (default: {"lr": 1e-4})
    pretrain_epochs : int
        number of epochs for the pretraining of the autoencoder (default: 100)
    clustering_epochs : int
        number of epochs for the actual clustering procedure. Will reset after each merge (default: 50)
    optimizer_class : torch.optim.Optimizer
        the optimizer class (default: torch.optim.Adam)
    loss_fn : torch.nn.modules.loss._Loss
        loss function for the reconstruction (default: torch.nn.MSELoss())
    autoencoder : torch.nn.Module
        the input autoencoder. If None a new FeedforwardAutoencoder will be created (default: None)
    embedding_size : int
        size of the embedding within the autoencoder (default: 10)
    max_cluster_size_diff_factor : float
        The maximum different in size when comparing two clusters regarding the number of samples.
        If one cluster surpasses this difference factor, only the max_cluster_size_diff_factor*(size of smaller cluster) closest samples will be used for the Dip calculation (default: 2)
    pval_strategy : str
        Defines which strategy to use to receive dip-p-vales. Possibilities are 'table', 'function' and 'bootstrap' (default: 'table')
    n_boots : int
        Number of bootstraps used to calculate dip-p-values. Only necessary if pval_strategy is 'bootstrap' (default: 1000)
    custom_dataloaders : tuple
        tuple consisting of a trainloader (random order) at the first and a test loader (non-random order) at the second position.
        If None, the default dataloaders will be used (default: None)
    augmentation_invariance : bool
        If True, augmented samples provided in custom_dataloaders[0] will be used to learn
        cluster assignments that are invariant to the augmentation transformations (default: False)
    initial_clustering_class : ClusterMixin
        clustering class to obtain the initial cluster labels after the pretraining (default: KMeans)
    initial_clustering_params : dict
        parameters for the initial clustering class (default: {})
    random_state : np.random.RandomState
        use a fixed random state to get a repeatable solution. Can also be of type int (default: None)
    debug : bool
        If true, additional information will be printed to the console (default: False)

    Attributes
    ----------
    labels_ : np.ndarray
        The final labels
    n_clusters_ : int
        The final number of clusters
    cluster_centers_ : np.ndarray
        The final cluster centers
    autoencoder : torch.nn.Module
        The final autoencoder

    Examples
    ----------
    >>> from clustpy.data import create_subspace_data
    >>> from clustpy.deep import DipDECK
    >>> data, labels = create_subspace_data(1500, subspace_features=(3, 50), random_state=1)
    >>> dipdeck = DipDECK(pretrain_epochs=3, clustering_epochs=3)
    >>> dipdeck.fit(data)

    References
    ----------
    Leiber, Collin, et al. "Dip-based deep embedded clustering with k-estimation."
    Proceedings of the 27th ACM SIGKDD Conference on Knowledge Discovery & Data Mining. 2021.
    """

    def __init__(self, n_clusters_init: int = 35, dip_merge_threshold: float = 0.9, cluster_loss_weight: float = 1,
                 max_n_clusters: int = np.inf, min_n_clusters: int = 1, batch_size: int = 256,
                 pretrain_optimizer_params: dict = {"lr": 1e-3}, clustering_optimizer_params: dict = {"lr": 1e-4},
                 pretrain_epochs: int = 100, clustering_epochs: int = 50,
                 optimizer_class: torch.optim.Optimizer = torch.optim.Adam,
                 loss_fn: torch.nn.modules.loss._Loss = torch.nn.MSELoss(), autoencoder: torch.nn.Module = None,
                 embedding_size: int = 5, max_cluster_size_diff_factor: float = 2, pval_strategy: str = "table",
                 n_boots: int = 1000, custom_dataloaders: tuple = None, augmentation_invariance: bool = False,
                 initial_clustering_class: ClusterMixin = KMeans, initial_clustering_params: dict = {},
                 random_state: np.random.RandomState = None, debug: bool = False):
        self.n_clusters_init = n_clusters_init
        self.dip_merge_threshold = dip_merge_threshold
        self.cluster_loss_weight = cluster_loss_weight
        self.max_n_clusters = max_n_clusters
        self.min_n_clusters = min_n_clusters
        self.batch_size = batch_size
        self.pretrain_optimizer_params = pretrain_optimizer_params
        self.clustering_optimizer_params = clustering_optimizer_params
        self.pretrain_epochs = pretrain_epochs
        self.clustering_epochs = clustering_epochs
        self.optimizer_class = optimizer_class
        self.loss_fn = loss_fn
        self.autoencoder = autoencoder
        self.embedding_size = embedding_size
        self.max_cluster_size_diff_factor = max_cluster_size_diff_factor
        self.pval_strategy = pval_strategy
        self.n_boots = n_boots
        self.custom_dataloaders = custom_dataloaders
        self.augmentation_invariance = augmentation_invariance
        self.initial_clustering_class = initial_clustering_class
        self.initial_clustering_params = initial_clustering_params
        self.random_state = check_random_state(random_state)
        set_torch_seed(self.random_state)
        self.debug = debug

    def fit(self, X: np.ndarray, y: np.ndarray = None) -> 'DipDECK':
        """
        Initiate the actual clustering process on the input data set.
        The resulting cluster labels will be stored in the labels_ attribute.

        Parameters
        ----------
        X : np.ndarray
            the given data set
        y : np.ndarray
            the labels (can be ignored)

        Returns
        -------
        self : DipDECK
            this instance of the DipDECK algorithm
        """
        augmentation_invariance_check(self.augmentation_invariance, self.custom_dataloaders)
        labels, n_clusters, centers, autoencoder = _dip_deck(X, self.n_clusters_init, self.dip_merge_threshold,
                                                             self.cluster_loss_weight, self.max_n_clusters,
                                                             self.min_n_clusters, self.batch_size,
                                                             self.pretrain_optimizer_params,
                                                             self.clustering_optimizer_params,
                                                             self.pretrain_epochs, self.clustering_epochs,
                                                             self.optimizer_class, self.loss_fn, self.autoencoder,
                                                             self.embedding_size, self.max_cluster_size_diff_factor,
                                                             self.pval_strategy, self.n_boots, self.custom_dataloaders,
                                                             self.augmentation_invariance,
                                                             self.initial_clustering_class,
                                                             self.initial_clustering_params, self.random_state,
                                                             self.debug)
        self.labels_ = labels
        self.n_clusters_ = n_clusters
        self.cluster_centers_ = centers
        self.autoencoder = autoencoder
        return self

    def predict(self, X: np.ndarray) -> np.ndarray:
        """
        Predicts the labels of the input data.

        Parameters
        ----------
        X : np.ndarray
            input data

        Returns
        -------
        predicted_labels : np.ndarray
            The predicted labels
        """
        # Get embedded centers
        device = detect_device()
        centerloader = get_dataloader(self.cluster_centers_, self.batch_size, False, False)
        embedded_centers = encode_batchwise(centerloader, self.autoencoder, device)
        # Get labels
        dataloader = get_dataloader(X, self.batch_size, False, False)
        predicted_labels = embedded_kmeans_prediction(dataloader, embedded_centers, self.autoencoder)
        return predicted_labels
