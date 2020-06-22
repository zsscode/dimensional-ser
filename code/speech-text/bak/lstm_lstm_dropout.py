# lstm_lstm: emotion recognition from speech= lstm, text=lstm
# created for ATSIT paper 2020
# coded by Bagus Tris Atmaja (bagus@ep.its.ac.id)

import numpy as np
import pickle
import pandas as pd

import keras.backend as K
from keras.models import Model, Sequential
from keras.layers import Input, Dense, Masking, CuDNNLSTM, TimeDistributed, \
                         Bidirectional, Flatten, \
                         Embedding, Dropout, Flatten, BatchNormalization, \
                         RNN, concatenate, Activation
from keras.callbacks import EarlyStopping
from keras.preprocessing import sequence
from sklearn.preprocessing import StandardScaler, MinMaxScaler, RobustScaler
from keras.wrappers.scikit_learn import KerasRegressor

import random as rn
import tensorflow as tf

from sklearn.model_selection import GridSearchCV

rn.seed(123)
np.random.seed(99)
tf.set_random_seed(1234)

# load feature and labels
feat = np.load('/home/s1820002/atsit/data/feat_34_hfs.npy')
vad = np.load('/home/s1820002/IEMOCAP-Emotion-Detection/y_egemaps.npy')

# remove outlier, < 1, > 5
vad = np.where(vad==5.5, 5.0, vad)
vad = np.where(vad==0.5, 1.0, vad)

# standardization
scaled_feature = False

# text feature
path = '/home/s1820002/IEMOCAP-Emotion-Detection/'
x_train_text = np.load(path+'x_train_text.npy')
g_word_embedding_matrix = np.load(path+'g_word_embedding_matrix.npy')

# other parameters
MAX_SEQUENCE_LENGTH = 554
EMBEDDING_DIM = 300
nb_words = 3438


# set Dropout
do = 0.3

if scaled_feature == True:
    scaler = StandardScaler()
    scaler = scaler.fit(feat.reshape(feat.shape[0]*feat.shape[1], feat.shape[2]))
    scaled_feat = scaler.transform(feat.reshape(feat.shape[0]*feat.shape[1], feat.shape[2]))
    scaled_feat = scaled_feat.reshape(feat.shape[0], feat.shape[1], feat.shape[2])
    feat = scaled_feat
else:
    feat = feat

scaled_vad = True

# standardization
if scaled_vad:
    scaler = MinMaxScaler(feature_range=(-1, 1))
    scaler = scaler.fit(vad) #.reshape(vad.shape[0]*vad.shape[1], vad.shape[2]))
    scaled_vad = scaler.transform(vad) #.reshape(vad.shape[0]*vad.shape[1], vad.shape[2]))
    vad = scaled_vad 
else:
    vad = vad

# Concordance correlation coefficient (CCC)-based loss function - using non-inductive statistics
def ccc(gold, pred):
    gold       = K.squeeze(gold, axis=-1)
    pred       = K.squeeze(pred, axis=-1)
    gold_mean  = K.mean(gold, axis=-1, keepdims=True)
    pred_mean  = K.mean(pred, axis=-1, keepdims=True)
    covariance = (gold-gold_mean)*(pred-pred_mean)
    gold_var   = K.mean(K.square(gold-gold_mean), axis=-1, keepdims=True)
    pred_var   = K.mean(K.square(pred-pred_mean), axis=-1, keepdims=True)
    ccc        = K.constant(2.) * covariance / (gold_var + pred_var + K.square(gold_mean - pred_mean) + K.common.epsilon())
    return ccc


def ccc_loss(gold, pred):  
    # input (num_batches, seq_len, 1)
    ccc_loss   = K.constant(1.) - ccc(gold, pred)
    return ccc_loss


# API model
def create_model():
    # speech network
    input_speech = Input(shape=(feat.shape[1], feat.shape[2]), name='speech_input')
    net_speech = BatchNormalization()(input_speech)
    net_speech = CuDNNLSTM(256, return_sequences=True)(net_speech)
    net_speech = CuDNNLSTM(256, return_sequences=True)(net_speech)
    net_speech = CuDNNLSTM(256, return_sequences=True)(net_speech)
    net_speech = Flatten()(net_speech)
    model_speech = Dropout(dropout_rate)(net_speech)
    
    #text network
    input_text = Input(shape=(MAX_SEQUENCE_LENGTH, ))
    net_text = Embedding(nb_words,
                    EMBEDDING_DIM,
                    weights = [g_word_embedding_matrix],
                    trainable = True)(input_text)
    net_text = CuDNNLSTM(256, return_sequences=True)(net_text)
    net_text = CuDNNLSTM(256, return_sequences=True)(net_text)
    net_text = CuDNNLSTM(256, return_sequences=False)(net_text)
    net_text = Dense(64)(net_text)
    model_text = Dropout(0.3)(net_text)

    # combined model
    model_combined = concatenate([model_speech, model_text])
    model_combined = Dense(64, activation='relu')(model_combined)
    model_combined = Dense(32, activation='relu')(model_combined)
    model_combined = Dropout(0.4)(model_combined)
    target_names = ('v', 'a', 'd')
    model_combined = [Dense(1, name=name)(model_combined) for name in target_names]

    model = Model([input_speech, input_text], model_combined) 
    model.compile(loss=ccc_loss,
                  loss_weights={'v': 1, 'a': 1, 'd': 1},
                  optimizer='rmsprop', metrics=[ccc])
    return model
    
#model = model(1,1,1)
#model.summary()

# 7869 first data of session 5 (for LOSO)
earlystop = EarlyStopping(monitor='val_loss', mode='min', patience=10,
                          restore_best_weights=True)
#hist = model.fit([feat[:7869], x_train_text[:7869]], 
#                  vad[:7869].T.tolist(), batch_size=8, #best:8
#                  validation_split=0.2, epochs=50, verbose=1, shuffle=True,
#                  callbacks=[earlystop])
#metrik = model.evaluate([feat[7869:], x_train_text[7869:]], vad[7869:].T.tolist())
#print(metrik)

model = KerasRegressor(build_fn=create_model, epochs=50, batch_size=8, 
                       verbose=0, callbacks=[earlystop])
                       
dropout_rate = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]
param_grid = dict(dropout_rate=dropout_rate)
grid = GridSearchCV(estimator=model, param_grid=param_grid, n_jobs=-1, cv=3)
grid_result = grid.fit([feat.T, x_train_text.T], 
                       vad.T.tolist())

# summarize results
print("Best: %f using %s" % (grid_result.best_score_, grid_result.best_params_))
means = grid_result.cv_results_[ccc]
#stds = grid_result.cv_results_['std_test_score']
params = grid_result.cv_results_['params']
for mean, stdev, param in zip(means, params):
    print("%f (%f) with: %r" % (mean, param))
