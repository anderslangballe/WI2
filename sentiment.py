import io
import math
import pickle
import random
import re
from collections import Counter

import bs4
import numpy as np
from loguru import logger
from nltk import word_tokenize
from nltk.corpus import stopwords

stop_words = set(stopwords.words('english'))


def class_from_score(score):
    score_classes = {
        '1.0': 0,
        '2.0': 0,
        '3.0': None,
        '4.0': 1,
        '5.0': 1,
    }

    return score_classes[score]


def load_sentiment_data(file_name):
    x, y = [], []

    current_class = None

    with io.open(file_name, mode='r', encoding='utf-8') as file:
        for line in file.readlines():
            split = [x.strip() for x in line.split(':')]

            if split[0] == 'review/score':
                current_class = class_from_score(split[1])
            elif split[0] == 'review/text' and current_class is not None:
                x.append(split[1])
                y.append(current_class)

                current_class = None

    return x, y


def shuffle_lists(*ls):
    zipped = list(zip(*ls))
    random.shuffle(zipped)
    return zip(*zipped)


def _undersample(x, y, random_state=0):
    random.seed = random_state

    x, y = shuffle_lists(x, y)

    # Get min class count
    counter = Counter(y)
    min_count = min(counter.values())

    # Undersample by taking min_count items from every class
    ret_x, ret_y = [], []
    for cls in counter.keys():
        cls_idx = set([idx for idx, val in enumerate(y) if val == cls][:min_count])

        ret_x.extend([val for idx, val in enumerate(x) if idx in cls_idx])
        ret_y.extend([cls] * min_count)

    return shuffle_lists(ret_x, ret_y)


def _preprocess(corpus):
    """ Remove HTML and perform negation. """
    punctuation = re.compile('[.:;!?]')
    negatives = {'don\'t', 'never', 'nothing', 'nowhere', 'noone', 'none', 'not', 'no', 'hasn\'t', 'hadn\'t', 'can\'t',
                 'couldn\'t', 'shouldn\'t', 'won\'t', 'wouldn\'t', 'don\'t', 'doesn\'t', 'didn\'t', 'isn\'t', 'aren\'t',
                 'ain\'t'}

    ret_corpus = []

    for text in corpus:
        text = text.lower().split()  # Remove HTML and split newlines
        new_text = []

        negate = False
        for word in text:
            new_text.append(word if not negate else f'neg_{word}')

            if word in negatives:
                negate = True
            elif punctuation.findall(word):
                negate = False

        ret_corpus.append(' '.join(new_text))

    return ret_corpus


def naive_bayes():
    classes = {0, 1}
    train_x, train_y = load_sentiment_data('SentimentTrainingData.txt')
    test_x, test_y = load_sentiment_data('SentimentTestingData.txt')
    logger.debug('Loaded training and testing data')

    # Undersample
    train_x, train_y = _undersample(train_x, train_y)
    test_x, test_y = _undersample(test_x, test_y)

    train_x = [preprocessing(text) for text in train_x]
    test_x = [preprocessing(text) for text in test_x]
    logger.debug('Preprocessed training and test data')

    # Create vocabulary
    vocab = create_vocabulary(train_x)

    # Generate vocabulary index
    vocab_index = {}
    for i in range(len(vocab)):
        vocab_index[vocab[i]] = i

    logger.info('Created vocabulary')

    class_prob = {}
    num_data = len(train_y)

    # Calculate the probability of a class
    for cls in classes:
        count = train_y.count(cls)
        class_prob[cls] = math.log(count / num_data)  # Use log such that no underflow occur
    logger.debug('Calculated class probability')

    # Count the number of occurrences for each term over all reviews
    term_freq_matrix = count_term_occurrence(train_x, train_y, classes, vocab_index)
    logger.debug('Calculated term count for each class')

    # Get the number of terms in each class
    terms_per_class = np.sum(term_freq_matrix, axis=0)

    # Create term count vectors
    matrix = count_vectorizer(vocab, test_x, vocab_index)

    # Predict the class of test labels
    predictions = []
    for i in range(len(matrix)):
        predictions.append(predict(matrix[i], term_freq_matrix, terms_per_class, class_prob))

    logger.debug('Predicted classes on test set')

    acc, precision_pos, precision_neg, recall_pos, recall_neg = get_measures(predictions, test_y)

    # Save model parts
    with open('model.pkl', 'wb') as f:
        pickle.dump({'vocabulary': vocab, 'vocabulary_index': vocab_index, 'term_frequency_per_class': term_freq_matrix,
                     'terms_per_class': terms_per_class, 'class_probability': class_prob}, f)

    # Save measures
    with open("results_no_under.pkl", 'wb') as f:
        pickle.dump({'accuracy': acc, 'precision_pos': precision_pos, 'recall_pos': recall_pos,
                     'precision_neg': precision_neg, 'recall_neg': recall_neg}, f)


def get_measures(predictions, labels):
    acc = len([1 for pred, label in zip(predictions, labels) if pred == label]) / len(labels)

    # Get the different measures.
    precision_pos = get_precision(predictions, labels, 1)
    precision_neg = get_precision(predictions, labels, 0)
    recall_pos = get_recall(predictions, labels, 1)
    recall_neg = get_recall(predictions, labels, 0)

    return acc, precision_pos, precision_neg, recall_pos, recall_neg


def get_precision(predictions, labels, _class):
    retrieved = 0
    true_guess = 0

    # Count all documents matching the class and count where these were correct.
    for pred, label in zip(predictions, labels):
        if pred == _class:
            retrieved += 1

            if pred == label:
                true_guess += 1

    return true_guess / retrieved


def get_recall(predictions, labels, _class):
    relevant = 0
    true_guess = 0

    # Count all real matches with the class and count how many were correctly guessed.
    for pred, label in zip(predictions, labels):
        if label == _class:
            relevant += 1

            if pred == label:
                true_guess += 1

    return true_guess / relevant


def create_vocabulary(reviews):
    vocab = set()

    # Create vocabulary of terms
    for review in reviews:
        for term in review:
            vocab.add(term)

    return sorted(list(vocab))


def count_vectorizer(vocab, data, vocab_index):
    length = len(vocab)

    matrix = []

    # For each review count the term occurrence frequency
    for review in data:
        count_map = np.zeros((length,))
        for term in review:
            if term in vocab_index:
                count_map[vocab_index[term]] += 1

        matrix.append(count_map)

    return matrix


def count_term_occurrence(data, labels, classes, vocab_index: dict):
    vocab_length = len(vocab_index.items())
    matrix = np.zeros((vocab_length, len(classes)))

    # for each text/review count the number of occurrences for each class
    for text, label in zip(data, labels):
        for term in text:
            # Skips if not in dictionary.
            if term not in vocab_index:
                continue

            index = vocab_index[term]

            matrix[index][label] += 1

    return matrix


def predict(vector, term_freq_matrix, num_terms_pr_class, class_prob):
    class_scores = np.zeros((len(num_terms_pr_class)))
    class_instances = len(num_terms_pr_class)
    vector_length = len(vector)  # Vocabulary size

    # For each term calculate the probability using log. Log is used to insure no underflow as
    # the standard formula Pi(p(x_i | c)) would be a small number. We therefore get the log probability,
    # we can compare on
    for term_index in range(vector_length):
        for class_index in range(class_instances):
            if vector[term_index] != 0:
                # Uses Laplace smoothing to ensure no log of 0
                class_scores[class_index] += math.log((term_freq_matrix[term_index][class_index] + 1) /
                                                      (num_terms_pr_class[class_index] + vector_length))

    # Add the class probability
    for class_index in range(len(num_terms_pr_class)):
        class_scores[class_index] += class_prob[class_index]

    class_scores = list(class_scores)

    # Return the label of the vector
    return class_scores.index(max(class_scores))


def preprocessing(text):
    """ Tokenizes a string, and NOP the tokens

    Arguments:
        string {str} -- A string of words.

    Returns:
        list -- A list containing stemmed tokens.
    """
    punctuation = re.compile('[.:;!?]')
    negatives = {'dont', 'never', 'nothing', 'nowhere', 'noone', 'none', 'not', 'no', 'hasnt', 'hadnt', 'cant',
                 'couldnt', 'shouldnt', 'wont', 'wouldnt', 'dont', 'doesnt', 'didnt', 'isnt', 'arent',
                 'aint'}

    # Convert document to lowercase and replace apostrophes
    # Apostrophes are removed because Treebank style tokenization splits them from their word
    text = text.lower().replace('\'', '')

    # Remove HTML
    soup = bs4.BeautifulSoup(text, 'html.parser')
    text = soup.text

    tokenized = word_tokenize(text)

    # Add negation prepends
    tokens_with_negation = []
    negate = False
    for token in tokenized:
        # Continue if stop word
        if token in stop_words:
            if punctuation.findall(token):
                negate = False

            continue

        # Check if token contains alphanumerical characters
        if not re.match(r'\w+', token):
            continue

        tokens_with_negation.append(token if not negate else f'NEG_{token}')

        if token in negatives:
            negate = True

    return tokens_with_negation


if __name__ == "__main__":
    naive_bayes()
