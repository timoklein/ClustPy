import torch
from itertools import islice
import numpy as np
import random
from sklearn.base import ClusterMixin
import inspect
from sklearn.metrics.pairwise import pairwise_distances_argmin_min
import os


def set_torch_seed(random_state: np.random.RandomState) -> None:
    """
    Set the random state for torch applications.

    Parameters
    ----------
    random_state : np.random.RandomState
        use a fixed random state to get a repeatable solution
    """
    seed = random_state.get_state()[1][0]
    torch.manual_seed(seed)
    torch.cuda.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    np.random.seed(seed)
    random.seed(seed)


def squared_euclidean_distance(tensor1: torch.Tensor, tensor2: torch.Tensor,
                               weights: torch.Tensor = None) -> torch.Tensor:
    """
    Calculate the pairwise squared euclidean distance between two tensors.
    Each row in the tensors is interpreted as a separate object, while each column represents its features.
    Therefore, the result of an (4x3) and (12x3) tensor will be a (4x12) tensor.
    Optionally, features can be individually weighted.
    The default behavior is that all features are weighted by 1.

    Parameters
    ----------
    tensor1 : torch.Tensor
        the first tensor
    tensor2 : torch.Tensor
        the second tensor
    weights : torch.Tensor
        tensor containing the weights of the features (default: None)

    Returns
    -------
    squared_diffs : torch.Tensor
        the pairwise squared euclidean distances
    """
    assert tensor1.shape[1] == tensor2.shape[1], "The number of features of the two input tensors must match."
    ta = tensor1.unsqueeze(1)
    tb = tensor2.unsqueeze(0)
    squared_diffs = (ta - tb)
    if weights is not None:
        assert tensor1.shape[1] == weights.shape[0]
        weights_unsqueezed = weights.unsqueeze(0).unsqueeze(1)
        squared_diffs = squared_diffs * weights_unsqueezed
    squared_diffs = squared_diffs.pow(2).sum(2)
    return squared_diffs


def detect_device(device: torch.device = None) -> torch.device:
    """
    Automatically detects if you have a cuda enabled GPU.
    Device can also be read from environment variable "CLUSTPY_DEVICE".
    It can be set using, e.g., os.environ["CLUSTPY_DEVICE"] = "cuda:1"

    Parameters
    ----------
    device : torch.device
        the input device. Will be returned if it is not None (default: None)

    Returns
    -------
    device : torch.device
        device on which the prediction should take place
    """
    if device is None:
        env_device = os.environ.get("CLUSTPY_DEVICE", None)
        # Check if environment device is None
        if env_device is None:
            if torch.cuda.is_available():
                device = torch.device('cuda')
            else:
                device = torch.device('cpu')
        else:
            device = torch.device(env_device)
    return device


def encode_batchwise(dataloader: torch.utils.data.DataLoader, module: torch.nn.Module,
                     device: torch.device) -> np.ndarray:
    """
    Utility function for embedding the whole data set in a mini-batch fashion

    Parameters
    ----------
    dataloader : torch.utils.data.DataLoader
        dataloader to be used
    module : torch.nn.Module
        the module that is used for the encoding (e.g. an autoencoder)
    device : torch.device
        device to be trained on

    Returns
    -------
    embeddings_numpy : np.ndarray
        The embedded data set
    """
    embeddings = []
    for batch in dataloader:
        batch_data = batch[1].to(device)
        embeddings.append(module.encode(batch_data).detach().cpu())
    embeddings_numpy = torch.cat(embeddings, dim=0).numpy()
    return embeddings_numpy


def decode_batchwise(dataloader: torch.utils.data.DataLoader, module: torch.nn.Module,
                     device: torch.device) -> np.ndarray:
    """
    Utility function for decoding the whole data set in a mini-batch fashion with an autoencoder.
    Note: Assumes an implemented decode function

    Parameters
    ----------
    dataloader : torch.utils.data.DataLoader
        dataloader to be used
    module : torch.nn.Module
        the module that is used for the decoding (e.g. an autoencoder)
    device : torch.device
        device to be trained on

    Returns
    -------
    reconstructions_numpy : np.ndarray
        The reconstructed data set
    """
    reconstructions = []
    for batch in dataloader:
        batch_data = batch[1].to(device)
        embedding = module.encode(batch_data)
        reconstructions.append(module.decode(embedding).detach().cpu())
    reconstructions_numpy = torch.cat(reconstructions, dim=0).numpy()
    return reconstructions_numpy


def encode_decode_batchwise(dataloader: torch.utils.data.DataLoader, module: torch.nn.Module,
                            device: torch.device) -> (np.ndarray, np.ndarray):
    """
    Utility function for encoding and decoding the whole data set in a mini-batch fashion with an autoencoder.
    Note: Assumes an implemented decode function

    Parameters
    ----------
    dataloader : torch.utils.data.DataLoader
        dataloader to be used
    module : torch.nn.Module
        the module that is used for the encoding and decoding (e.g. an autoencoder)
    device : torch.device
        device to be trained on

    Returns
    -------
    tuple : (np.ndarray, np.ndarray)
        The embedded data set,
        The reconstructed data set
    """
    embeddings = []
    reconstructions = []
    for batch in dataloader:
        batch_data = batch[1].to(device)
        embedding = module.encode(batch_data)
        embeddings.append(embedding.detach().cpu())
        reconstructions.append(module.decode(embedding).detach().cpu())
    embeddings_numpy = torch.cat(embeddings, dim=0).numpy()
    reconstructions_numpy = torch.cat(reconstructions, dim=0).numpy()
    return embeddings_numpy, reconstructions_numpy


def predict_batchwise(dataloader: torch.utils.data.DataLoader, module: torch.nn.Module, cluster_module: torch.nn.Module,
                      device: torch.device) -> np.ndarray:
    """
    Utility function for predicting the cluster labels over the whole data set in a mini-batch fashion.
    Method calls the predict_hard method of the cluster_module for each batch of data.

    Parameters
    ----------
    dataloader : torch.utils.data.DataLoader
        dataloader to be used
    module : torch.nn.Module
        the module that is used for the encoding (e.g. an autoencoder)
    cluster_module : torch.nn.Module
        the cluster module that is used for the encoding (e.g. DEC). Usually contains the predict method.
    device : torch.device
        device to be trained on

    Returns
    -------
    predictions_numpy : np.ndarray
        The predictions of the cluster_module for the data set
    """
    predictions = []
    for batch in dataloader:
        batch_data = batch[1].to(device)
        prediction = cluster_module.predict_hard(module.encode(batch_data)).detach().cpu()
        predictions.append(prediction)
    predictions_numpy = torch.cat(predictions, dim=0).numpy()
    return predictions_numpy


def window(seq, n):
    """Returns a sliding window (of width n) over data from the following iterable:
       s -> (s0,s1,...s[n-1]), (s1,s2,...,sn), ..."""
    it = iter(seq)
    result = tuple(islice(it, n))
    if len(result) == n:
        yield result
    for elem in it:
        result = result[1:] + (elem,)
        yield result


# def add_noise(batch):
#     mask = torch.empty(
#         batch.shape, device=batch.device).bernoulli_(0.8)
#     return batch * mask


def int_to_one_hot(int_tensor: torch.Tensor, n_integers: int) -> torch.Tensor:
    """
    Convert a tensor containing integers (e.g. labels) to an one hot encoding.
    Here, each integer gets its own features in the resulting tensor, where only the values 0 or 1 are accepted.
    E.g. [0,0,1,2,1] gets
    [[1,0,0],
    [1,0,0],
    [0,1,0],
    [0,0,1],
    [0,1,0]]

    Parameters
    ----------
    int_tensor : torch.Tensor
        The original tensor containing integers
    n_integers : int
        The number of different integers within int_tensor

    Returns
    -------
    onehot : torch.Tensor
        The final one hot encoding tensor
    """
    onehot = torch.zeros([int_tensor.shape[0], n_integers], dtype=torch.float, device=int_tensor.device)
    onehot.scatter_(1, int_tensor.unsqueeze(1).long(), 1)
    return onehot


def embedded_kmeans_prediction(dataloader: torch.utils.data.DataLoader, cluster_centers: np.ndarray,
                               module: torch.nn.Module) -> np.ndarray:
    """
    Predicts the labels of the data within the given dataloader.
    Labels correspond to the id of the closest cluster center.

    Parameters
    ----------
    dataloader : torch.utils.data.DataLoader
        dataloader to be used
    cluster_centers : np.ndarray
        input cluster centers
    module : torch.nn.Module
        the module that is used for the encoding (e.g. an autoencoder)

    Returns
    -------
    predicted_labels : np.ndarray
        The predicted labels
    """
    device = detect_device()
    embedded_data = encode_batchwise(dataloader, module, device)
    predicted_labels, _ = pairwise_distances_argmin_min(X=embedded_data, Y=cluster_centers, metric='euclidean',
                                                        metric_kwargs={'squared': True})
    return predicted_labels


def run_initial_clustering(X: np.ndarray, n_clusters: int, clustering_class: ClusterMixin, clustering_params: dict,
                           random_state: np.random.RandomState) -> (int, np.ndarray, np.ndarray, ClusterMixin):
    """
    Get an initial clustering result for a deep clustering algorithm.
    This result can then be refined by the optimization of the autoencoder.

    Parameters
    ----------
    X : np.ndarray
        the given data set
    n_clusters : int
        number of clusters. Can be None if a corresponding initial_clustering_class is given, e.g. DBSCAN
    clustering_class : ClusterMixin
        the class of the initial clustering algorithm
    clustering_params : dict
        the parameters for the initial clustering algorithm
    random_state : np.random.RandomState
        use a fixed random state to get a repeatable solution

    Returns
    -------
    tuple : (int, np.ndarray, np.ndarray, ClusterMixin)
        The number of clusters (can change if e.g. DBSCAN is used)
        The initial cluster labels,
        The initial cluster centers,
        The clustering object
    """
    # Get possible input parameters of the clustering algorithm
    clustering_class_parameters = inspect.getfullargspec(clustering_class).args + inspect.getfullargspec(
        clustering_class).kwonlyargs
    # Check if n_clusters or n_components is contained in the possible parameters
    if "n_clusters" in clustering_class_parameters:
        if "random_state" in clustering_class_parameters:
            clustering_algo = clustering_class(n_clusters=n_clusters, random_state=random_state, **clustering_params)
        else:
            clustering_algo = clustering_class(n_clusters=n_clusters, **clustering_params)
    elif "n_components" in clustering_class_parameters:  # in case of GMM
        if "random_state" in clustering_class_parameters:
            clustering_algo = clustering_class(n_components=n_clusters, random_state=random_state, **clustering_params)
        else:
            clustering_algo = clustering_class(n_components=n_clusters, **clustering_params)
    else:  # in case of e.g., DBSCAN
        if "random_state" in clustering_class_parameters:
            clustering_algo = clustering_class(random_state=random_state, **clustering_params)
        else:
            clustering_algo = clustering_class(**clustering_params)
    # Run algorithm
    clustering_algo.fit(X)
    # Check if clustering algorithm return cluster centers
    if hasattr(clustering_algo, "cluster_centers_"):
        labels = clustering_algo.labels_
        centers = clustering_algo.cluster_centers_
    elif hasattr(clustering_algo, "means_"):  # in case of GMM
        labels = clustering_algo.predict(X)
        centers = clustering_algo.means_
    else:  # in case of e.g., DBSCAN
        labels = clustering_algo.labels_
        centers = np.array([np.mean(X[labels == i], axis=0) for i in np.unique(labels) if i >= 0])
    n_clusters = np.sum(np.unique(labels) >= 0)  # Needed for DBSCAN, XMeans, GMeans, ...
    return n_clusters, labels, centers, clustering_algo
