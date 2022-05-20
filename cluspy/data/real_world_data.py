import urllib.request
import os
from pathlib import Path
import ssl
import numpy as np
import zipfile
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import LabelEncoder
from sklearn.datasets import fetch_20newsgroups, fetch_rcv1, load_iris as sk_load_iris, load_wine as sk_load_wine, \
    load_breast_cancer as sk_load_breast_cancer
import pandas as pd

DEFAULT_DOWNLOAD_PATH = str(Path.home() / "Downloads/cluspy_datafiles")


# More datasets https://www.csie.ntu.edu.tw/~cjlin/libsvmtools/datasets/multiclass.html#usps

def _get_download_dir(downloads_path):
    """
    Helper function to define the path where the data files should be stored. If downloads_path is None then default path
    '[USER]/Downloads/cluspy_datafiles' will be used. If the directory does not exists it will be created.

    Parameters
    ----------
    downloads_path: path to the directory where the data will be stored. Can be None

    Returns
    -------
    path to the directory where the data will be stored. If input was None this will be equal to
    '[USER]/Downloads/cluspy_datafiles'
    """
    if downloads_path is None:
        downloads_path = DEFAULT_DOWNLOAD_PATH
    if not os.path.isdir(downloads_path):
        os.makedirs(downloads_path)
    return downloads_path


def _download_file(file_url, filename_local):
    """
    Helper function to download a file into a specified location.

    Parameters
    ----------
    file_url: URL of the file
    filename_local: local name of the file after it has been downloaded
    """
    print("Downloading data set from {0} to {1}".format(file_url, filename_local))
    ssl._create_default_https_context = ssl._create_unverified_context
    urllib.request.urlretrieve(file_url, filename_local)
    ssl._create_default_https_context = ssl._create_default_https_context


def _load_data_file(filename_local, file_url, delimiter=",", last_column_are_labels=True):
    """
    Helper function to load a data file. Either the first or last column, depending on last_column_are_labels, of the
    data file is used as the label column.
    If file does not exist on the local machine it will be downloaded.

    Parameters
    ----------
    filename_local: local name of the file after it has been downloaded
    file_url: URL of the file
    delimiter: delimiter in the data file (default: ";")
    last_column_are_labels: specifies if the last column contains the labels. If false labels should be contained in
    the first column

    Returns
    -------
    data: the data numpy array
    labels: the labels numpy array
    """
    if not os.path.isfile(filename_local):
        _download_file(file_url, filename_local)
    datafile = np.genfromtxt(filename_local, delimiter=delimiter)
    if last_column_are_labels:
        data = datafile[:, :-1]
        labels = datafile[:, -1]
    else:
        data = datafile[:, 1:]
        labels = datafile[:, 0]
    return data, labels


def _load_timeseries_classification_data(dataset_name, subset, labels_minus_one, downloads_path):
    """
    Helper function to load timeseries data from www.timeseriesclassification.com.

    Parameters
    ----------
    dataset_name: name of the data set
    subset: can be 'all', 'test' or 'train'. 'all' combines test and train data
    labels_minus_one: Convert labels from 1,... to 0,...
    downloads_path: path to the directory where the data is stored

    Returns
    -------
    data: the data numpy array
    labels: the labels numpy array
    """
    assert subset in ["all", "train",
                      "test"], "subset must match 'all', 'train' or 'test' Your input {0}".format(subset)
    directory = _get_download_dir(downloads_path) + "/" + dataset_name + "/"
    filename = directory + dataset_name + ".zip"
    if not os.path.isfile(filename):
        if not os.path.isdir(directory):
            os.mkdir(directory)
        _download_file("http://www.timeseriesclassification.com/Downloads/" + dataset_name + ".zip",
                       filename)
        # Unpack zipfile
        with zipfile.ZipFile(filename, 'r') as zipf:
            zipf.extractall(directory)
    # Load data and labels
    if subset == "all" or subset == "train":
        dataset = np.genfromtxt(directory + dataset_name + "_TRAIN.txt")
        data = dataset[:, 1:]
        labels = dataset[:, 0]
    if subset == "all" or subset == "test":
        test_dataset = np.genfromtxt(directory + dataset_name + "_TEST.txt")
        if subset == "all":
            data = np.r_[data, test_dataset[:, 1:]]
            labels = np.r_[labels, test_dataset[:, 0]]
        else:
            data = test_dataset[:, 1:]
            labels = test_dataset[:, 0]
    if labels_minus_one:
        # Convert labels from 1,... to 0,...
        labels -= 1
    return data, labels


def _decompress_z_file(filename, directory):
    """
    Helper function to decompress a 7z file. The function uses an installed version of 7zip to decompress the file.
    If 7zip is not installed on this machine, the function will return False and a warning is printed.

    Parameters
    ----------
    filename: name of the file that should be decompressed
    directory: directory of the file that should be decompressed

    Returns
    -------
    True if decompression was successful, else False
    """
    os.system("7z x {0} -o{1}".format(filename.replace("\\", "/"), directory.replace("\\", "/")))
    if os.path.isfile(filename[:-2]):
        # If file without .z exists, decompression was successful
        return True
    else:
        print("[WARNING] 7Zip is needed to uncompress *.Z files!")
        return False


"""
Load Sklearn datasets
"""


def load_iris():
    """
    Load the iris data set. It consists of the petal and sepal width and length of three different types of irises (Setosa,
    Versicolour, Virginica).
    N=150, d=4, k=3.

    Returns
    -------
    data: the data numpy array (150 x 4)
    labels: the labels numpy array (150)

    References
    -------
    https://scikit-learn.org/stable/modules/generated/sklearn.datasets.load_iris.html
    https://archive.ics.uci.edu/ml/datasets/iris
    """
    return sk_load_iris(return_X_y=True)


def load_wine():
    """
    Load the wine data set. It consists of 13 different properties of three different types of wine.
    N=178, d=13, k=3.

    Returns
    -------
    data: the data numpy array (178 x 13)
    labels: the labels numpy array (178)

    References
    -------
    https://scikit-learn.org/stable/modules/generated/sklearn.datasets.load_wine.html
    https://archive.ics.uci.edu/ml/datasets/wine
    """
    return sk_load_wine(return_X_y=True)


def load_breast_cancer():
    """
    Load the breast cancer wisconsin data set. It consists of 32 features computed from digitized images of fine needle
    aspirate of breast mass. The classes are the result of a diagnosis (malignant or benign).
    N=569, d=30, k=2.

    Returns
    -------
    data: the data numpy array (569 x 30)
    labels: the labels numpy array (569)

    References
    -------
    https://scikit-learn.org/stable/modules/generated/sklearn.datasets.load_breast_cancer.html#sklearn.datasets.load_breast_cancer
    https://archive.ics.uci.edu/ml/datasets/breast+cancer+wisconsin+(diagnostic)
    """
    return sk_load_breast_cancer(return_X_y=True)


def load_newsgroups(subset="all", n_features=2000):
    """
    Load the 20 newsgroups data set. It consists of a collection of 18846 newsgroup documents, partitioned
    (nearly) evenly across 20 different newsgroups. The documents are converted into feature vectors using TF-IDF.
    The data set is composed of 11314 training and 7532 test documents.
    N=18846, d=2000, k=20 using the default settings.

    Parameters
    ----------
    subset: can be 'all', 'test' or 'train'. 'all' combines test and train data (default: 'all')
    n_features: number of features used by TF-IDF (default: 2000)

    Returns
    -------
    data: the data numpy array (18846 x 2000) using the default settings
    labels: the labels numpy array (18846)

    References
    -------
    https://scikit-learn.org/stable/modules/generated/sklearn.datasets.fetch_20newsgroups.html#sklearn.datasets.fetch_20newsgroups
    http://qwone.com/~jason/20Newsgroups/
    """
    newsgroups = fetch_20newsgroups(subset=subset, remove=('headers', 'footers', 'quotes'))
    vectorizer = TfidfVectorizer(max_features=n_features, dtype=np.float64, sublinear_tf=True)
    data_sparse = vectorizer.fit_transform(newsgroups.data)
    data = np.asarray(data_sparse.todense())
    labels = newsgroups.target
    return data, labels


def load_reuters(subset="all", n_features=2000, categories=["CCAT", "GCAT", "MCAT", "ECAT"]):
    """
    Load the Reuters data set. It consists of over 800000 manually categorized newswire stories made available by Reuters,
    Ltd. Usually only a subset of the categories is used. Those categories are defined by the attribute 'categories'.
    We use only those articles that belong to a single category. Further, we only use the n_features most frequent
    features.
    The data set is composed of 19806 training and 665265 test documents using the default settings.
    N=685071, d=2000, k=4 using the default settings.

    Parameters
    ----------
    add_testdata: can be 'all', 'test' or 'train'. 'all' combines test and train data (default: 'all')
    n_features: number of features used (default: 2000)
    categories: the categories that should be contained (default: ["CCAT", "GCAT", "MCAT", "ECAT"])

    Returns
    -------
    data: the data numpy array (685071 x 2000) using the default settings
    labels: the labels numpy array (685071) using the default settings

    References
    -------
    https://scikit-learn.org/stable/modules/generated/sklearn.datasets.fetch_rcv1.html#sklearn.datasets.fetch_rcv1

    and

    Lewis, David D., et al. "Rcv1: A new benchmark collection for text categorization research." Journal of machine
    learning research 5.Apr (2004): 361-397.
    """
    reuters = fetch_rcv1(subset=subset)
    # Get samples with relevant main categories
    relevant_cats = [i for i, tn in enumerate(reuters.target_names) if tn in categories]
    filtered_labels = reuters.target[:, relevant_cats]
    # Only get documents with single category
    sum_of_labelings = np.sum(filtered_labels, axis=1)
    single_doc_ids = np.where(sum_of_labelings == 1)[0]
    # Get category of these documents
    labels = np.argmax(filtered_labels[single_doc_ids], axis=1)
    labels = np.asarray(labels)[:, 0]
    for i, cat in enumerate(relevant_cats):
        labels[labels == cat] = i
    # Get most frequent columns
    reuters_data = reuters.data[single_doc_ids]
    frequencies = np.asarray(np.sum(reuters_data, axis=0))[0]
    sorted_frequencies = np.argsort(frequencies)[::-1]
    selected_features = sorted_frequencies[:n_features]
    data = np.asarray(reuters_data[:, selected_features].todense())
    return data, labels


"""
Load UCI data
"""


def load_banknotes(downloads_path=None):
    """
    Load the banknote authentication data set. It consists of 1372 genuine and forged banknote samples.
    N=1372, d=4, k=2.

    Parameters
    ----------
    downloads_path: path to the directory where the data is stored (default: None -> [USER]/Downloads/cluspy_datafiles)

    Returns
    -------
    data: the data numpy array (1372 x 4)
    labels: the labels numpy array (1372)

    References
    -------
    https://archive.ics.uci.edu/ml/datasets/banknote+authentication
    """
    filename = _get_download_dir(downloads_path) + "/data_banknote_authentication.txt"
    data, labels = _load_data_file(filename,
                                   "https://archive.ics.uci.edu/ml/machine-learning-databases/00267/data_banknote_authentication.txt")
    return data, labels


def load_spambase(downloads_path=None):
    """
    Load the spambase data set. It consists of 4601 spam and non-spam mails.
    N=4601, d=57, k=2.

    Parameters
    ----------
    downloads_path: path to the directory where the data is stored (default: None -> [USER]/Downloads/cluspy_datafiles)

    Returns
    -------
    data: the data numpy array (4601 x 57)
    labels: the labels numpy array (4601)

    References
    -------
    https://archive.ics.uci.edu/ml/datasets/spambase
    """
    filename = _get_download_dir(downloads_path) + "/spambase.data"
    data, labels = _load_data_file(filename,
                                   "https://archive.ics.uci.edu/ml/machine-learning-databases/spambase/spambase.data")
    return data, labels


def load_seeds(downloads_path=None):
    """
    Load the seeds data set. It consists of 210 samples belonging to one of three varieties of wheat.
    N=210, d=7, k=3.

    Parameters
    ----------
    downloads_path: path to the directory where the data is stored (default: None -> [USER]/Downloads/cluspy_datafiles)

    Returns
    -------
    data: the data numpy array (210 x 7)
    labels: the labels numpy array (210)

    References
    -------
    https://archive.ics.uci.edu/ml/datasets/seeds
    """
    filename = _get_download_dir(downloads_path) + "/seeds_dataset.txt"
    data, labels = _load_data_file(filename,
                                   "https://archive.ics.uci.edu/ml/machine-learning-databases/00236/seeds_dataset.txt",
                                   delimiter=None)
    # Convert labels from 1,... to 0,...
    labels -= 1
    return data, labels


def load_skin(downloads_path=None):
    """
    Load the Skin Segmentation data set. It consists of 245057 skin- and non-skin samples with their B, G, R color
    information.
    N=245057, d=3, k=2.

    Parameters
    ----------
    downloads_path: path to the directory where the data is stored (default: None -> [USER]/Downloads/cluspy_datafiles)

    Returns
    -------
    data: the data numpy array (245057 x 3)
    labels: the labels numpy array (245057)

    References
    -------
    https://archive.ics.uci.edu/ml/datasets/skin+segmentation
    """
    filename = _get_download_dir(downloads_path) + "/Skin_NonSkin.txt"
    data, labels = _load_data_file(filename,
                                   "https://archive.ics.uci.edu/ml/machine-learning-databases/00229/Skin_NonSkin.txt",
                                   delimiter=None)
    # Convert labels from 1,... to 0,...
    labels -= 1
    return data, labels


def load_soybean_small(downloads_path=None):
    """
    Load the small version of the soybean data set. It is a small subset of the original soybean data set.
    It consists of 47 samples belonging to one of 4 classes.
    N=47, d=35, k=4.

    Parameters
    ----------
    downloads_path: path to the directory where the data is stored (default: None -> [USER]/Downloads/cluspy_datafiles)

    Returns
    -------
    data: the data numpy array (47 x 35)
    labels: the labels numpy array (47)

    References
    -------
    https://archive.ics.uci.edu/ml/datasets/soybean+(small)
    """
    filename = _get_download_dir(downloads_path) + "/soybean-small.data"
    if not os.path.isfile(filename):
        _download_file(
            "https://archive.ics.uci.edu/ml/machine-learning-databases/soybean/soybean-small.data",
            filename)
    # Load data and labels
    df = pd.read_csv(filename, delimiter=",", header=None)
    labels_raw = df.iloc[:, -1]
    data = df.iloc[:, :-1].values
    LE = LabelEncoder()
    labels = LE.fit_transform(labels_raw)
    return data, labels


def load_soybean_large(subset="all", downloads_path=None):
    """
    Load the large version of the soybean data set. It consists of 562 samples belonging to one of 15 classes.
    Originally, the data set would have samples and 19 classes but some samples have attributes showing '?' values. Those
    will be ignored.
    The data set is composed of 266 training and 296 test samples.
    N=562, d=35, k=15.

    Parameters
    ----------
    subset: can be 'all', 'test' or 'train'. 'all' combines test and train data (default: 'all')
    downloads_path: path to the directory where the data is stored (default: None -> [USER]/Downloads/cluspy_datafiles)

    Returns
    -------
    data: the data numpy array (562 x 35)
    labels: the labels numpy array (562)

    References
    -------
    https://archive.ics.uci.edu/ml/datasets/soybean+(Large)
    """
    assert subset in ["all", "train",
                      "test"], "subset must match 'all', 'train' or 'test' Your input {0}".format(subset)
    if subset == "all" or subset == "train":
        filename = _get_download_dir(downloads_path) + "/soybean-large.data"
        if not os.path.isfile(filename):
            _download_file(
                "https://archive.ics.uci.edu/ml/machine-learning-databases/soybean/soybean-large.data",
                filename)
        # Load data and labels
        df_train = pd.read_csv(filename, delimiter=",", header=None)
        df_train = df_train[(df_train != '?').all(axis=1)]
        labels_raw = df_train.pop(0)
        data = df_train.values
    if subset == "all" or subset == "test":
        filename = _get_download_dir(downloads_path) + "/soybean-large.test"
        if not os.path.isfile(filename):
            _download_file(
                "https://archive.ics.uci.edu/ml/machine-learning-databases/soybean/soybean-large.test",
                filename)
        df_test = pd.read_csv(filename, delimiter=",", header=None)
        df_test = df_test[(df_test != '?').all(axis=1)]
        labels_test = df_test.pop(0)
        if subset == "all":
            data = np.r_[data, df_test.values]
            labels_raw = np.r_[labels_raw, labels_test]
        else:
            data = df_test.values
            labels_raw = labels_test
    # Transform data to numerical array
    data = np.array(data, dtype=np.int)
    LE = LabelEncoder()
    labels = LE.fit_transform(labels_raw)
    return data, labels


def load_optdigits(subset="all", downloads_path=None):
    """
    Load the optdigits data set. It consists of 5620 8x8 grayscale images, each representing a digit (0 to 9).
    Each pixel depicts the number of marked pixel within a 4x4 block of the original 32x32 bitmaps.
    The data set is composed of 3823 training and 1797 test samples.
    N=5620, d=64, k=10.

    Parameters
    ----------
    subset: can be 'all', 'test' or 'train'. 'all' combines test and train data (default: 'all')
    downloads_path: path to the directory where the data is stored (default: None -> [USER]/Downloads/cluspy_datafiles)

    Returns
    -------
    data: the data numpy array (5620 x 64)
    labels: the labels numpy array (5620)

    References
    -------
    http://archive.ics.uci.edu/ml/datasets/optical+recognition+of+handwritten+digits
    """
    assert subset in ["all", "train",
                      "test"], "subset must match 'all', 'train' or 'test' Your input {0}".format(subset)
    if subset == "all" or subset == "train":
        filename = _get_download_dir(downloads_path) + "/optdigits.tra"
        data, labels = _load_data_file(filename,
                                       "https://archive.ics.uci.edu/ml/machine-learning-databases/optdigits/optdigits.tra")
    if subset == "all" or subset == "test":
        filename = _get_download_dir(downloads_path) + "/optdigits.tes"
        test_data, test_labels = _load_data_file(filename,
                                                 "https://archive.ics.uci.edu/ml/machine-learning-databases/optdigits/optdigits.tes")
        if subset == "all":
            data = np.r_[data, test_data]
            labels = np.r_[labels, test_labels]
        else:
            data = test_data
            labels = test_labels
    return data, labels


def load_pendigits(subset="all", downloads_path=None):
    """
    Load the pendigits data set. It consists of 10992 vectors of length 16, representing 8 coordinates. The coordinates
    were taken from the task of writing digits (0 to 9) on a tablet.
    The data set is composed of 7494 training and 3498 test samples.
    N=10992, d=16, k=10.

    Parameters
    ----------
    subset: can be 'all', 'test' or 'train'. 'all' combines test and train data (default: 'all')
    downloads_path: path to the directory where the data is stored (default: None -> [USER]/Downloads/cluspy_datafiles)

    Returns
    -------
    data: the data numpy array (10992 x 16)
    labels: the labels numpy array (10992)

    References
    -------
    http://archive.ics.uci.edu/ml/datasets/pen-based+recognition+of+handwritten+digits
    """
    assert subset in ["all", "train",
                      "test"], "subset must match 'all', 'train' or 'test' Your input {0}".format(subset)
    if subset == "all" or subset == "train":
        filename = _get_download_dir(downloads_path) + "/pendigits.tra"
        data, labels = _load_data_file(filename,
                                       "https://archive.ics.uci.edu/ml/machine-learning-databases/pendigits/pendigits.tra")
    if subset == "all" or subset == "test":
        filename = _get_download_dir(downloads_path) + "/pendigits.tes"
        test_data, test_labels = _load_data_file(filename,
                                                 "https://archive.ics.uci.edu/ml/machine-learning-databases/pendigits/pendigits.tes")
        if subset == "all":
            data = np.r_[data, test_data]
            labels = np.r_[labels, test_labels]
        else:
            data = test_data
            labels = test_labels
    return data, labels


def load_ecoli(ignore_small_clusters=False, downloads_path=None):
    """
    Load the ecoli data set. It consists of 336 samples belonging to one of 8 classes.
    N=336, d=7, k=8.

    Parameters
    ----------
    ignore_small_clusters: specify if the three small clusters with size 2, 2 and 5 should be ignored (default: False)
    downloads_path: path to the directory where the data is stored (default: None -> [USER]/Downloads/cluspy_datafiles)

    Returns
    -------
    data: the data numpy array (336 x 7)
    labels: the labels numpy array (336)

    References
    -------
    https://archive.ics.uci.edu/ml/datasets/ecoli
    """
    filename = _get_download_dir(downloads_path) + "/ecoli.data"
    if not os.path.isfile(filename):
        _download_file(
            "https://archive.ics.uci.edu/ml/machine-learning-databases/ecoli/ecoli.data",
            filename)
    data = np.zeros((336, 7))
    labels_raw = []
    with open(filename, "r") as f:
        for i, line in enumerate(f.readlines()):
            splited = line.split()
            data[i] = splited[1:-1]
            labels_raw.append(splited[-1])
    if ignore_small_clusters:
        # Optional: Remove the three small clusters consisting of only 2, 2 and 5 samples
        keep_labels = [l not in ["imL", "imS", "omL"] for l in labels_raw]
        data = data[keep_labels]
        labels_raw = [l for i, l in enumerate(labels_raw) if keep_labels[i]]
    LE = LabelEncoder()
    labels = LE.fit_transform(labels_raw)
    return data, labels


def load_htru2(downloads_path=None):
    """
    Load the HTRU2 data set. It consists of 17898 samples belonging to the pulsar or non-pulsar class.
    A special property is that more than 90% of the data belongs to class 0.

    N=17898, d=8, k=2.

    Parameters
    ----------
    downloads_path: path to the directory where the data is stored (default: None -> [USER]/Downloads/cluspy_datafiles)

    Returns
    -------
    data: the data numpy array (17898 x 8)
    labels: the labels numpy array (17898)

    References
    -------
    https://archive.ics.uci.edu/ml/datasets/HTRU2
    """
    directory = _get_download_dir(downloads_path) + "/htru2/"
    filename = directory + "HTRU2.zip"
    if not os.path.isfile(filename):
        if not os.path.isdir(directory):
            os.mkdir(directory)
        _download_file("https://archive.ics.uci.edu/ml/machine-learning-databases/00372/HTRU2.zip",
                       filename)
        # Unpack zipfile
        with zipfile.ZipFile(filename, 'r') as zipf:
            zipf.extractall(directory)
    # Load data and labels
    dataset = np.genfromtxt(directory + "HTRU_2.csv", delimiter=",")
    data = dataset[:, :-1]
    labels = dataset[:, -1]
    return data, labels


def load_letterrecognition(downloads_path=None):
    """
    Load the Letter Recognition data set. It consists of 20000 samples where each sample represents one of the 26 capital
    letters in the English alphabet. All samples are composed of 16 numerical stimuli describing the respective letter.
    N=20000, d=16, k=26.

    Parameters
    ----------
    downloads_path: path to the directory where the data is stored (default: None -> [USER]/Downloads/cluspy_datafiles)

    Returns
    -------
    data: the data numpy array (20000 x 16)
    labels: the labels numpy array (20000)

    References
    -------
    https://archive.ics.uci.edu/ml/datasets/letter+recognition
    """
    filename = _get_download_dir(downloads_path) + "/letter-recognition.data"
    if not os.path.isfile(filename):
        _download_file(
            "https://archive.ics.uci.edu/ml/machine-learning-databases/letter-recognition/letter-recognition.data",
            filename)
    # Transform letters to integers
    letter_mappings = {"A": "0", "B": "1", "C": "2", "D": "3", "E": "4", "F": "5", "G": "6", "H": "7", "I": "8",
                       "J": "9", "K": "10", "L": "11", "M": "12", "N": "13", "O": "14", "P": "15", "Q": "16",
                       "R": "17", "S": "18", "T": "19", "U": "20", "V": "21", "W": "22", "X": "23", "Y": "24",
                       "Z": "25"}
    with open(filename, "r") as f:
        file_text = f.read()
    file_text = file_text.replace("\n", ",")
    for k in letter_mappings.keys():
        file_text = file_text.replace(k, letter_mappings[k])
    # Create numpy array
    datafile = np.fromstring(file_text, sep=",").reshape(-1, 17)
    data = datafile[:, 1:]
    labels = datafile[:, 0]
    return data, labels


def load_har(subset="all", downloads_path=None):
    """
    Load the Human Activity Recognition data set. It consists of 10299 samples each representing sensor data of a person
    performing an activity. The six activities are walking, walking_upstairs, walking_downstairs, sitting, standing and
    laying.
    The data set is composed of 7352 training and 2947 test samples.
    N=10992, d=561, k=6.

    Parameters
    ----------
    subset: can be 'all', 'test' or 'train'. 'all' combines test and train data (default: 'all')
    downloads_path: path to the directory where the data is stored (default: None -> [USER]/Downloads/cluspy_datafiles)

    Returns
    -------
    data: the data numpy array (10992 x 561)
    labels: the labels numpy array (10992)

    References
    -------
    https://archive.ics.uci.edu/ml/datasets/human+activity+recognition+using+smartphones
    """
    assert subset in ["all", "train",
                      "test"], "subset must match 'all', 'train' or 'test' Your input {0}".format(subset)
    directory = _get_download_dir(downloads_path) + "/har/"
    filename = directory + "UCI HAR Dataset.zip"
    if not os.path.isfile(filename):
        if not os.path.isdir(directory):
            os.mkdir(directory)
        _download_file("https://archive.ics.uci.edu/ml/machine-learning-databases/00240/UCI%20HAR%20Dataset.zip",
                       filename)
        # Unpack zipfile
        with zipfile.ZipFile(filename, 'r') as zipf:
            zipf.extractall(directory)
    # Load data and labels
    if subset == "all" or subset == "train":
        data = np.genfromtxt(directory + "UCI HAR Dataset/train/X_train.txt")
        labels = np.genfromtxt(directory + "UCI HAR Dataset/train/y_train.txt")
    if subset == "all" or subset == "test":
        test_data = np.genfromtxt(directory + "UCI HAR Dataset/test/X_test.txt")
        test_labels = np.genfromtxt(directory + "UCI HAR Dataset/test/y_test.txt")
        if subset == "all":
            data = np.r_[data, test_data]
            labels = np.r_[labels, test_labels]
        else:
            data = test_data
            labels = test_labels
    # Convert labels from 1,... to 0,...
    labels = labels - 1
    return data, labels


def load_statlog_shuttle(subset="all", downloads_path=None):
    """
    Load the statlog shuttle data set. It consists of 58000 samples belonging to one of 7 classes. A special property is
    that about 80% of the data belongs to class 0.
    The data set is composed of 43500 training and 14500 test samples.
    N=58000, d=9, k=7.

    Parameters
    ----------
    subset: can be 'all', 'test' or 'train'. 'all' combines test and train data (default: 'all')
    downloads_path: path to the directory where the data is stored (default: None -> [USER]/Downloads/cluspy_datafiles)

    Returns
    -------
    data: the data numpy array (58000 x 9)
    labels: the labels numpy array (58000)

    References
    -------
    https://archive.ics.uci.edu/ml/datasets/Statlog+(Shuttle)
    """
    assert subset in ["all", "train",
                      "test"], "subset must match 'all', 'train' or 'test' Your input {0}".format(subset)
    directory = _get_download_dir(downloads_path) + "/shuttle/"
    if subset == "all" or subset == "train":
        filename = directory + "shuttle.trn.Z"
        if not os.path.isfile(filename):
            if not os.path.isdir(directory):
                os.mkdir(directory)
            _download_file("https://archive.ics.uci.edu/ml/machine-learning-databases/statlog/shuttle/shuttle.trn.Z",
                           filename)
            # Unpack z-file
            success = _decompress_z_file(filename, directory)
            if not success:
                # os.remove(filename)
                return None, None
        # Load data and labels
        dataset = np.genfromtxt(directory + "shuttle.trn")
        data = dataset[:, :-1]
        labels = dataset[:, -1]
    if subset == "all" or subset == "test":
        filename = directory + "shuttle.tst"
        if not os.path.isfile(filename):
            _download_file(
                "https://archive.ics.uci.edu/ml/machine-learning-databases/statlog/shuttle/shuttle.tst",
                filename)
        test_dataset = np.genfromtxt(directory + "shuttle.tst")
        test_data = test_dataset[:, :-1]
        test_labels = test_dataset[:, -1]
        if subset == "all":
            data = np.r_[data, test_data]
            labels = np.r_[labels, test_labels]
        else:
            data = test_data
            labels = test_labels
    # Convert labels from 1,... to 0,...
    labels -= 1
    return data, labels


def load_mice_protein(return_additional_labels=False, downloads_path=None):
    """
    Load the Mice Protein Expression data set. It consists of 1077 samples belonging to one of 8 classes.
    Each features represents the expression level of one of 77 proteins.
    Samples containing more than 43 NaN values (3 cases) will be removed. Afterwards, all columns containing NaN values
    will be removed. This reduces the number of features from 77 to 68.
    The classes can be further subdivided by using the return_additional_labels parameter. This gives the additional
    information mouseID, behavior, treatment type and genotype.
    N=1077, d=68, k=8.

    Parameters
    ----------
    return_additional_labels: return additional labels (default: False)
    downloads_path: path to the directory where the data is stored (default: None -> [USER]/Downloads/cluspy_datafiles)

    Returns
    -------
    data: the data numpy array (1077 x 68)
    labels: the labels numpy array (1077)

    References
    -------
    https://archive.ics.uci.edu/ml/datasets/Mice+Protein+Expression
    """
    filename = _get_download_dir(downloads_path) + "/Data_Cortex_Nuclear.xls"
    if not os.path.isfile(filename):
        _download_file("https://archive.ics.uci.edu/ml/machine-learning-databases/00342/Data_Cortex_Nuclear.xls",
                       filename)
    xls = pd.ExcelFile(filename)
    # Load first page
    sheet = xls.parse(0)
    # Remove special columns
    classes_raw = sheet.pop("class")
    ids_raw = sheet.pop("MouseID")
    bahaviors_raw = sheet.pop("Behavior")
    treatments_raw = sheet.pop("Treatment")
    genotypes_raw = sheet.pop("Genotype")
    original_data = sheet.values
    # Remove rows containing 43 NaN values (3 cases)
    n_of_nans_per_row = np.sum(np.isnan(original_data), axis=1)
    data = original_data[n_of_nans_per_row < 43]
    # Remove columns containing NaN values (removes 9 columns)
    n_of_nans_per_columns = np.sum(np.isnan(data), axis=0)
    data = data[:, n_of_nans_per_columns == 0]
    # Get labels
    LE = LabelEncoder()
    labels = LE.fit_transform(classes_raw)
    if return_additional_labels:
        ids = [entry.split("_")[0] for entry in ids_raw]
        LE = LabelEncoder()
        id_labels = LE.fit_transform(ids)
        LE = LabelEncoder()
        bahaviors_labels = LE.fit_transform(bahaviors_raw)
        LE = LabelEncoder()
        treatment_labels = LE.fit_transform(treatments_raw)
        LE = LabelEncoder()
        genotype_labels = LE.fit_transform(genotypes_raw)
        labels = np.c_[labels, id_labels, bahaviors_labels, treatment_labels, genotype_labels]
    # Remove rows also from labels (3 cases)
    labels = labels[n_of_nans_per_row < 43]
    return data, labels


def load_user_knowledge(subset="all", downloads_path=None):
    """
    Load the user knowledge data set. It consists of 403 samples belonging to one of 4 classes.
    The 4 classes are the knowledge levels 'very low', 'low', 'middle' and 'high'.
    The data set is composed of 258 training and 145 test samples.
    N=403, d=5, k=4.

    Parameters
    ----------
    subset: can be 'all', 'test' or 'train'. 'all' combines test and train data (default: 'all')
    downloads_path: path to the directory where the data is stored (default: None -> [USER]/Downloads/cluspy_datafiles)

    Returns
    -------
    data: the data numpy array (403 x 5)
    labels: the labels numpy array (403)

    References
    -------
    https://archive.ics.uci.edu/ml/datasets/User+Knowledge+Modeling
    """
    assert subset in ["all", "train",
                      "test"], "subset must match 'all', 'train' or 'test' Your input {0}".format(subset)
    filename = _get_download_dir(downloads_path) + "/Data_User_Modeling_Dataset_Hamdi Tolga KAHRAMAN.xls"
    if not os.path.isfile(filename):
        _download_file(
            "https://archive.ics.uci.edu/ml/machine-learning-databases/00257/Data_User_Modeling_Dataset_Hamdi%20Tolga%20KAHRAMAN.xls",
            filename)
    xls = pd.ExcelFile(filename)
    if subset == "all" or subset == "train":
        # Load second page
        sheet_train = xls.parse(1)
        # Get data and label columns
        labels_raw = sheet_train.pop(" UNS")
        data = sheet_train.values[:, :5]
    if subset == "all" or subset == "test":
        # Load third page
        sheet_test = xls.parse(2)
        # Get data and label columns
        test_data = sheet_test.values[:, :5]
        uns_test = sheet_test.pop(" UNS")
        # Fix label string 'Very Low' to 'very_low' (as in train file)
        uns_test = [l.replace("Very Low", "very_low") for l in uns_test]
        if subset == "all":
            data = np.r_[data, test_data]
            labels_raw = np.r_[labels_raw, uns_test]
        else:
            data = test_data
            labels_raw = uns_test
    # Transform labels
    LE = LabelEncoder()
    labels = LE.fit_transform(labels_raw)
    return data, labels


def load_breast_tissue(downloads_path=None):
    """
    Load the breast tissue data set. It consists of 106 samples belonging to one of 6 classes.
    N=106, d=9, k=6.

    Parameters
    ----------
    downloads_path: path to the directory where the data is stored (default: None -> [USER]/Downloads/cluspy_datafiles)

    Returns
    -------
    data: the data numpy array (106 x 9)
    labels: the labels numpy array (106)

    References
    -------
    http://archive.ics.uci.edu/ml/datasets/breast+tissue
    """
    filename = _get_download_dir(downloads_path) + "/BreastTissue.xls"
    if not os.path.isfile(filename):
        _download_file("http://archive.ics.uci.edu/ml/machine-learning-databases/00192/BreastTissue.xls",
                       filename)
    xls = pd.ExcelFile(filename)
    # Load second page
    sheet = xls.parse(1)
    # Get data and label columns
    class_column = sheet.pop("Class")
    data = sheet.values[:, 1:]
    # Transform labels
    LE = LabelEncoder()
    labels = LE.fit_transform(class_column)
    return data, labels


def load_forest_types(subset="all", downloads_path=None):
    """
    Load the forest type mapping data set. It consists of 523 samples belonging to one of 4 classes.
    The data set is composed of 198 training and 325 test samples.
    N=523, d=27, k=4.

    Parameters
    ----------
    subset: can be 'all', 'test' or 'train'. 'all' combines test and train data (default: 'all')
    downloads_path: path to the directory where the data is stored (default: None -> [USER]/Downloads/cluspy_datafiles)

    Returns
    -------
    data: the data numpy array (523 x 27)
    labels: the labels numpy array (523)

    References
    -------
    https://archive.ics.uci.edu/ml/datasets/Forest+type+mapping
    """
    assert subset in ["all", "train",
                      "test"], "subset must match 'all', 'train' or 'test' Your input {0}".format(subset)
    directory = _get_download_dir(downloads_path) + "/ForestTypes/"
    filename = directory + "ForestTypes.zip"
    if not os.path.isfile(filename):
        if not os.path.isdir(directory):
            os.mkdir(directory)
        _download_file("https://archive.ics.uci.edu/ml/machine-learning-databases/00333/ForestTypes.zip",
                       filename)
        # Unpack zipfile
        with zipfile.ZipFile(filename, 'r') as zipf:
            zipf.extractall(directory)
    # Load data and labels
    if subset == "all" or subset == "train":
        df_train = pd.read_csv(directory + "/training.csv", delimiter=",")
        labels_raw = df_train.pop("class")
        data = df_train.values
    if subset == "all" or subset == "test":
        df_test = pd.read_csv(directory + "/testing.csv", delimiter=",")
        labels_test = df_test.pop("class")
        if subset == "all":
            data = np.r_[data, df_test.values]
            labels_raw = np.r_[labels_raw, labels_test]
        else:
            data = df_test.values
            labels_raw = labels_test
    # Transform labels
    LE = LabelEncoder()
    labels = LE.fit_transform(labels_raw)
    return data, labels


"""
Load timeseries classification data
"""


def load_motestrain(subset="all", downloads_path=None):
    """
    Load the motestrain data set. It consists of 1272 samples belonging to one of 2 classes.
    The data set is composed of 20 training and 1252 test samples.
    N=1272, d=84, k=2.

    Parameters
    ----------
    subset: can be 'all', 'test' or 'train'. 'all' combines test and train data (default: 'all')
    downloads_path: path to the directory where the data is stored (default: None -> [USER]/Downloads/cluspy_datafiles)

    Returns
    -------
    data: the data numpy array (1272 x 84)
    labels: the labels numpy array (1272)

    References
    -------
    http://www.timeseriesclassification.com/description.php?Dataset=MoteStrain
    """
    data, labels = _load_timeseries_classification_data("MoteStrain", subset, True, downloads_path)
    return data, labels


def load_proximal_phalanx_outline(subset="all", downloads_path=None):
    """
    Load the proximal phalanx outline data set. It consists of 876 samples belonging to one of 2 classes.
    The data set is composed of 600 training and 276 test samples.
    N=876, d=80, k=2.

    Parameters
    ----------
    subset: can be 'all', 'test' or 'train'. 'all' combines test and train data (default: 'all')
    downloads_path: path to the directory where the data is stored (default: None -> [USER]/Downloads/cluspy_datafiles)

    Returns
    -------
    data: the data numpy array (876 x 80)
    labels: the labels numpy array (876)

    References
    -------
    http://www.timeseriesclassification.com/description.php?Dataset=ProximalPhalanxOutlineCorrect
    """
    data, labels = _load_timeseries_classification_data("DistalPhalanxOutlineCorrect", subset, False, downloads_path)
    return data, labels


def load_diatom_size_reduction(subset="all", downloads_path=None):
    """
    Load the diatom size reduction data set. It consists of 322 samples belonging to one of 4 classes.
    The data set is composed of 16 training and 306 test samples.
    N=322, d=345, k=4.

    Parameters
    ----------
    subset: can be 'all', 'test' or 'train'. 'all' combines test and train data (default: 'all')
    downloads_path: path to the directory where the data is stored (default: None -> [USER]/Downloads/cluspy_datafiles)

    Returns
    -------
    data: the data numpy array (322 x 345)
    labels: the labels numpy array (322)

    References
    -------
    http://www.timeseriesclassification.com/description.php?Dataset=DiatomSizeReduction
    """
    data, labels = _load_timeseries_classification_data("DiatomSizeReduction", subset, True, downloads_path)
    return data, labels


def load_symbols(subset="all", downloads_path=None):
    """
    Load the symbols data set. It consists of 1020 samples belonging to one of 6 classes.
    The data set is composed of 25 training and 995 test samples.
    N=1020, d=398, k=6.

    Parameters
    ----------
    subset: can be 'all', 'test' or 'train'. 'all' combines test and train data (default: 'all')
    downloads_path: path to the directory where the data is stored (default: None -> [USER]/Downloads/cluspy_datafiles)

    Returns
    -------
    data: the data numpy array (1020 x 398)
    labels: the labels numpy array (1020)

    References
    -------
    http://www.timeseriesclassification.com/description.php?Dataset=Symbols
    """
    data, labels = _load_timeseries_classification_data("Symbols", subset, True, downloads_path)
    return data, labels


def load_olive_oil(subset="all", downloads_path=None):
    """
    Load the OliveOil data set. It consists of 60 samples belonging to one of 4 classes.
    The data set is composed of 30 training and 30 test samples.
    N=60, d=570, k=4.

    Parameters
    ----------
    subset: can be 'all', 'test' or 'train'. 'all' combines test and train data (default: 'all')
    downloads_path: path to the directory where the data is stored (default: None -> [USER]/Downloads/cluspy_datafiles)

    Returns
    -------
    data: the data numpy array (60 x 570)
    labels: the labels numpy array (60)

    References
    -------
    http://www.timeseriesclassification.com/description.php?Dataset=OliveOil
    """
    data, labels = _load_timeseries_classification_data("OliveOil", subset, True, downloads_path)
    return data, labels


def load_plane(subset="all", downloads_path=None):
    """
    Load the plane data set. It consists of 210 samples belonging to one of 7 classes.
    The data set is composed of 105 training and 105 test samples.
    N=210, d=144, k=7.

    Parameters
    ----------
    subset: can be 'all', 'test' or 'train'. 'all' combines test and train data (default: 'all')
    downloads_path: path to the directory where the data is stored (default: None -> [USER]/Downloads/cluspy_datafiles)

    Returns
    -------
    data: the data numpy array (210 x 144)
    labels: the labels numpy array (210)

    References
    -------
    http://www.timeseriesclassification.com/description.php?Dataset=Plane
    """
    data, labels = _load_timeseries_classification_data("Plane", subset, True, downloads_path)
    return data, labels
