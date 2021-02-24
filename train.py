#! /usr/bin/env python

from __future__ import absolute_import, division, print_function, unicode_literals

import sys, os
import json

sys.path.append("./")

import logging
import argparse
import numpy as np

import healpy as hp
from models.embedding import SphericalGraphCNN
from utils import create_mask as cm

import torch
from torch import nn

from sbi import utils
from sbi.inference import PosteriorEstimator, RatioEstimator

from pytorch_lightning.loggers import TensorBoardLogger, MLFlowLogger
import mlflow


def train(data_dir, experiment_name, sample_name, nside_max=128, r_outer=25, kernel_size=4, laplacian_type="combinatorial", fc_dims=[[-1, 2048], [2048, 512], [512, 96]], n_aux=2, maf_hidden_features=128, maf_num_transforms=8, batch_size=256, max_num_epochs=50, stop_after_epochs=8, clip_max_norm=1., validation_fraction=0.2, initial_lr=1e-3, device=None, optimizer_kwargs={'weight_decay': 1e-5}, method="snpe", summary=None, summary_range=None):

    # Cache hyperparameters to log
    params_to_log = locals()

    if device is None:
        device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")

    logging.info("")
    logging.info("")
    logging.info("")
    logging.info("Creating estimator")
    logging.info("")

    # Get mask of central pixel for nside=1
    hp_mask_nside1 = cm.make_mask_total(nside=1, band_mask=True, band_mask_range=0, mask_ring=True, inner=0, outer=r_outer)

    indexes_list = []
    masks_list = []

    assert (nside_max & (nside_max - 1) == 0) and nside_max != 0, "Invalid nside"

    nside_list = [int(nside_max / (2 ** i)) for i in np.arange(hp.nside2order(nside_max))]

    # Build indexes corresponding to subsequent nsides
    for nside in nside_list:
        hp_mask = hp.ud_grade(hp_mask_nside1, nside)
        masks_list.append(hp_mask)
        indexes_list.append(np.arange(hp.nside2npix(nside))[~hp_mask])

    # Priors hard-coded for now

    # iso, bub, psc, dif_pibrem, dif_ics
    prior_poiss = [[0.001, 0.001, 0.001, 6., 1.], [1.5, 1.5, 1.5, 12., 6.]]

    # gce, dsk
    prior_ps = [[0.001, 10.0, 1.1, -10.0, 5.0, 0.1, 0.001, 10.0, 1.1, -10.0, 5.0, 0.1], [2., 20.0, 1.99, 1.99, 50.0, 4.99, 2., 20.0, 1.99, 1.99, 50.0, 4.99]]

    # Combine priors
    prior = utils.BoxUniform(low=torch.tensor([0.001] + prior_poiss[0] + prior_ps[0]), high=torch.tensor([2.] + prior_poiss[1] + prior_ps[1]))

    # MLFlow logger
    tracking_uri = "file:{}/logs/mlruns".format(data_dir)
    mlf_logger = MLFlowLogger(experiment_name=experiment_name, tracking_uri=tracking_uri)
    mlf_logger.log_hyperparams(params_to_log)

    # Specify datasets

    if summary is None:
        x_filename = "{}/samples/x_{}.npy".format(data_dir, sample_name)
    else:
        x_filename = "{}/samples/x_{}_{}.npy".format(data_dir, summary, sample_name)  # If using a summary

    x_aux_filename = "{}/samples/x_aux_{}.npy".format(data_dir, sample_name)
    theta_filename = "{}/samples/theta_{}.npy".format(data_dir, sample_name)

    if method == "snpe":
        
        # Embedding net (feature extractor)
        sg_embed = SphericalGraphCNN(nside_list, indexes_list, kernel_size=kernel_size, laplacian_type=laplacian_type, fc_dims=fc_dims, n_aux=n_aux)

        # If using a summary stat, don't use (overwrite) feature extractor
        if summary is not None:
            sg_embed = nn.Identity()

        # Instantiate the neural density estimator
        density_estimator = utils.posterior_nn(model="maf", embedding_net=sg_embed, hidden_features=maf_hidden_features, num_transforms=maf_num_transforms,)

        # Setup the inference procedure with NPE
        posterior_estimator = PosteriorEstimator(prior=prior, density_estimator=density_estimator, show_progress_bars=True, logging_level="INFO", device=device.type, summary_writer=mlf_logger)

        # Model training
        density_estimator = posterior_estimator.train(x=x_filename, 
                                    x_aux=x_aux_filename, 
                                    theta=theta_filename, 
                                    proposal=prior, 
                                    training_batch_size=batch_size, 
                                    max_num_epochs=max_num_epochs, 
                                    stop_after_epochs=stop_after_epochs, 
                                    clip_max_norm=clip_max_norm,
                                    validation_fraction=validation_fraction,
                                    initial_lr=initial_lr,
                                    optimizer_kwargs=optimizer_kwargs,
                                    summary=summary,
                                    summary_range=summary_range)
        
        # Save density estimator
        mlflow.set_tracking_uri(tracking_uri)
        with mlflow.start_run(run_id=mlf_logger.run_id):
            mlflow.pytorch.log_model(density_estimator, "density_estimator")

        # Check to make sure model can be succesfully loaded
        model_uri = "runs:/{}/density_estimator".format(mlf_logger.run_id)
        density_estimator = mlflow.pytorch.load_model(model_uri)
        posterior = posterior_estimator.build_posterior(density_estimator)

    elif method == "snre":

        # Embedding net (feature extractor)
        sg_embed = SphericalGraphCNN(nside_list, indexes_list, kernel_size=kernel_size, laplacian_type=laplacian_type, fc_dims=fc_dims, n_aux=n_aux, n_params=18)

        # If using a summary stat, don't use (overwrite) feature extractor
        if summary is not None:
            sg_embed = nn.Identity()

        # Instantiate the neural density estimator
        neural_classifier = utils.classifier_nn(model="mlp_mixed", embedding_net_x=sg_embed)

        # Setup the inference procedure with NPE
        posterior_estimator = RatioEstimator(prior=prior, classifier=neural_classifier, show_progress_bars=True, logging_level="INFO", device=device.type, summary_writer=mlf_logger)

        # Model training
        density_estimator = posterior_estimator.train(x=x_filename, 
                                    x_aux=x_aux_filename, 
                                    theta=theta_filename, 
                                    proposal=prior, 
                                    training_batch_size=batch_size, 
                                    max_num_epochs=max_num_epochs, 
                                    stop_after_epochs=stop_after_epochs, 
                                    clip_max_norm=clip_max_norm,
                                    validation_fraction=validation_fraction,
                                    initial_lr=initial_lr,
                                    optimizer_kwargs=optimizer_kwargs)
        
        # Save density estimator
        mlflow.set_tracking_uri(tracking_uri)
        with mlflow.start_run(run_id=mlf_logger.run_id):
            mlflow.pytorch.log_model(density_estimator, "density_estimator")

        # Check to make sure model can be succesfully loaded
        model_uri = "runs:/{}/density_estimator".format(mlf_logger.run_id)
        density_estimator = mlflow.pytorch.load_model(model_uri)
        posterior = posterior_estimator.build_posterior(density_estimator)

def parse_args():
    parser = argparse.ArgumentParser(description="High-level script for the training of the neural likelihood ratio estimators")

    # Main options
    parser.add_argument("--sample", type=str, help='Sample name, like "train".')
    parser.add_argument("--summary", type=str, default=None, help='Whether using a summary statistic')
    parser.add_argument("--summary_range", type=str, default="None", help='Whether to use only a subset of the summary stats')
    parser.add_argument("--name", type=str, default='test', help='Experiment name.')
    parser.add_argument("--method", type=str, default='snpe', help='SBI method; "snpe" or "snre".')
    parser.add_argument("--fc_dims", type=str, default="[[-1, 2048], [2048, 512], [512, 96]]", help='Specification of fully-connected embedding layers')
    parser.add_argument("--maf_num_transforms", type=int, default=4, help="Number of MAF blocks")
    parser.add_argument("--batch_size", type=int, default=64, help="Training batch size.")
    parser.add_argument("--dir", type=str, default=".", help="Directory. Training data will be loaded from the data/samples subfolder, the model saved in the " "data/models subfolder.")

    # Training option
    return parser.parse_args()

if __name__ == "__main__":
    logging.basicConfig(
        format="%(asctime)-5.5s %(name)-20.20s %(levelname)-7.7s %(message)s", datefmt="%H:%M", level=logging.INFO,
    )
    logging.info("Hi!")

    args = parse_args()

    if args.summary_range != "None":
        args.summary_range = list(json.loads(args.summary_range))
    else:
        args.summary_range = None

    train(data_dir="{}/data/".format(args.dir), sample_name=args.sample, experiment_name=args.name, fc_dims=list(json.loads(args.fc_dims)), batch_size=args.batch_size, maf_num_transforms=args.maf_num_transforms, method=args.method, summary=args.summary, summary_range=args.summary_range)

    logging.info("All done! Have a nice day!")
