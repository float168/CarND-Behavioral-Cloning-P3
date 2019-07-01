import pathlib
import argparse
import sys
import os

import pandas
import cv2
import numpy

from keras.models import Sequential
from keras.layers import Lambda, Reshape, Cropping2D, Conv2D, MaxPool2D, BatchNormalization, Activation, Flatten, Dense
from keras.callbacks import EarlyStopping

import preprocess

#------------------------------------------------------------------------------
# Main
#------------------------------------------------------------------------------

def main():
    default_csv_path = pathlib.Path(__file__).parent / "data" / "driving_log.csv"

    # Parse args
    parser = argparse.ArgumentParser('train model with simulator data')
    parser.add_argument('-c', '--csv', type=pathlib.Path, nargs='*',
                        default=[default_csv_path],
                        help='CSV files generated by simulator')
    parser.add_argument('-l', '--list', action='store_true',
                        help='list the output shape of each model layer')
    args = parser.parse_args()

    # Build model
    input_shape = preprocess.INPUT_SHAPE
    model = create_model(input_shape)

    if args.list:
        for layer in model.layers:
            print(layer.output_shape)
        return 0

    # Load dataset
    dataset = None
    for csv_path in args.csv:
        if not csv_path.is_file:
            print('Error: not CSV file: {}', csv_path, file=sys.stderr)
            return 1
        ds = load_dataset(csv_path)
        if dataset is None:
            dataset = ds
        else:
            dataset = dataset.concat(ds)
    dataset = augment_dataset(dataset)

    # Train model
    early_stopping_callback = EarlyStopping('val_loss',
            patience=2, verbose=1, mode='auto')
    model.fit(dataset.X, dataset.y,
            batch_size=128,
            validation_split=0.1,
            shuffle=True,
            epochs=10,
            verbose=1,
            callbacks=[early_stopping_callback],
            )

    # Save model
    model.save('model.h5')

    return 0

#------------------------------------------------------------------------------
# Data
#------------------------------------------------------------------------------

class Dataset:
    def __init__(self, X, y):
        self.X = numpy.array(X, dtype='float32')
        self.y = numpy.array(y, dtype='float32')
        assert(len(self.X) == len(self.y))
        self.size = len(X)

    def __len__(self):
        return self.size

    # Concatenate another dataset to itself
    def concat(self, other):
        X = numpy.concatenate([self.X, other.X], axis=0)
        y = numpy.concatenate([self.y, other.y], axis=0)
        return Dataset(X, y)

    # Augment dataset by applying functions
    def augment(self, func_X, func_y):
        extra = Dataset(func_X(self.X), func_y(self.y))
        return self.concat(extra)

# Load dataset from CSV file
def load_dataset(csv_fname):
    df = pandas.read_csv(csv_fname, header=None, usecols=[0, 3]) # center, steering
    if df.iloc[0,0] == 'center':
        df = df.drop(0, axis=0)

    dir_path = pathlib.Path(csv_fname).parent
    def load_rgb(relative_fname):
        img_path = dir_path.joinpath(relative_fname)
        bgr = cv2.imread(str(img_path))
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        return rgb
    X = [load_rgb(fname) for fname in df.iloc[:, 0].values]
    X = [preprocess.preprocess(img) for img in X]

    y = df.iloc[:, 1].values

    return Dataset(X, y)

# Augment dataset using several functions
def augment_dataset(raw_dataset):
    # Horizontal flipping
    dataset = raw_dataset.augment(lambda X: numpy.flip(X, axis=2), lambda y: y * -1.0)

    return dataset

#------------------------------------------------------------------------------
# Model
#------------------------------------------------------------------------------

# Model definition
def create_model(input_shape):
    model = Sequential()

    # Input (Dummy layer which does nothing)
    model.add(Lambda(lambda x: x, input_shape=input_shape))

    # Convolution
    def conv_and_pool(model, n_filters):
        model.add(Conv2D(n_filters, 3, padding='same'))
        model.add(BatchNormalization())
        model.add(Activation('relu'))

        model.add(Conv2D(n_filters, 3, padding='same'))
        model.add(BatchNormalization())
        model.add(Activation('relu'))

        model.add(MaxPool2D(2))

    conv_and_pool(model, 32)
    conv_and_pool(model, 64)
    conv_and_pool(model, 128)
    conv_and_pool(model, 256)
    conv_and_pool(model, 512)

    model.add(Flatten())

    # Fully connected
    def dense(model, output_size):
        model.add(Dense(output_size))
        model.add(BatchNormalization())
        model.add(Activation('relu'))

    dense(model, 1024)
    dense(model, 256)
    dense(model, 64)

    # Output
    model.add(Dense(1))

    model.compile(loss='mse', optimizer='adam')

    return model


if __name__ == "__main__":
    retval = main()
    sys.exit(retval)
