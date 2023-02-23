def test_example_1():
    from cluspy.partition import SubKmeans
    from cluspy.data import create_subspace_data
    from cluspy.metrics import unsupervised_clustering_accuracy as acc

    data, labels = create_subspace_data(1000, n_clusters=4, subspace_features=[2, 5])
    sk = SubKmeans(4)
    sk.fit(data)
    acc_res = acc(labels, sk.labels_)
    print("Clustering accuracy:", acc_res)


def test_example_2():
    from cluspy.alternative import NrKmeans
    from cluspy.data import load_cmu_faces
    from cluspy.metrics import MultipleLabelingsConfusionMatrix
    from sklearn.metrics import normalized_mutual_info_score as nmi
    import numpy as np

    data, labels = load_cmu_faces()
    nk = NrKmeans([20, 4, 4, 2])
    nk.fit(data)
    mlcm = MultipleLabelingsConfusionMatrix(labels, nk.labels_, nmi)
    mlcm.rearrange()
    print(mlcm.confusion_matrix)
    print(np.max(mlcm.confusion_matrix, axis=1))


def test_example_3():
    from cluspy.deep import DEC
    from cluspy.data import load_optdigits
    from sklearn.metrics import adjusted_rand_score as ari

    data, labels = load_optdigits()
    dec = DEC(10, pretrain_epochs=10, clustering_epochs=10)
    dec.fit(data)
    my_ari = ari(labels, dec.labels_)
    print(my_ari)


def test_example_4():
    from cluspy.utils import EvaluationDataset, EvaluationAlgorithm, EvaluationMetric, evaluate_multiple_datasets
    from cluspy.partition import ProjectedDipMeans, SubKmeans
    from sklearn.metrics import normalized_mutual_info_score as nmi, silhouette_score
    from sklearn.cluster import KMeans, DBSCAN
    from cluspy.data import load_breast_cancer, load_iris, load_wine
    from cluspy.metrics import unsupervised_clustering_accuracy as acc
    from sklearn.decomposition import PCA
    import numpy as np

    def reduce_dimensionality(X, dims):
        pca = PCA(dims)
        X_new = pca.fit_transform(X)
        return X_new

    def znorm(X):
        return (X - np.mean(X)) / np.std(X)

    def minmax(X):
        return (X - np.min(X)) / (np.max(X) - np.min(X))

    datasets = [
        EvaluationDataset("Breast_pca_znorm", data=load_breast_cancer, preprocess_methods=[reduce_dimensionality, znorm],
                          preprocess_params=[{"dims": 0.9}, {}], ignore_algorithms=["pdipmeans"]),
        EvaluationDataset("Iris_pca", data=load_iris, preprocess_methods=reduce_dimensionality,
                          preprocess_params={"dims": 0.9}),
        EvaluationDataset("Wine", data=load_wine),
        EvaluationDataset("Wine_znorm", data=load_wine, preprocess_methods=znorm)]

    algorithms = [
        EvaluationAlgorithm("SubKmeans", SubKmeans, {"n_clusters": None}),
        EvaluationAlgorithm("pdipmeans", ProjectedDipMeans, {}),  # Determines n_clusters automatically
        EvaluationAlgorithm("dbscan", DBSCAN, {"eps": 0.01, "min_samples": 5}, preprocess_methods=minmax,
                            deterministic=True),
        EvaluationAlgorithm("kmeans", KMeans, {"n_clusters": None}),
        EvaluationAlgorithm("kmeans_minmax", KMeans, {"n_clusters": None}, preprocess_methods=minmax)]

    metrics = [EvaluationMetric("NMI", nmi), EvaluationMetric("ACC", acc),
               EvaluationMetric("Silhouette", silhouette_score, use_gt=False)]

    df = evaluate_multiple_datasets(datasets, algorithms, metrics, n_repetitions=5,
                                    aggregation_functions=[np.mean, np.std, np.max, np.min],
                                    add_runtime=True, add_n_clusters=True, save_path=None,
                                    save_intermediate_results=False)
    print(df)
