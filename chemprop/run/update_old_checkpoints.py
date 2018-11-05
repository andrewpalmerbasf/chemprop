from argparse import Namespace

import torch

from chemprop.model import build_model
from chemprop.io.parsing import parse_train_args
from chemprop.utils.utils import get_data, split_data, save_checkpoint, StandardScaler


def update_old_checkpoint(args: Namespace):
    """Updates an old checkpoint (just state dict) to a new checkpoint with args and scaler."""
    # Load data
    data = get_data(args.data_path, args)

    # Split data
    if args.dataset_type == 'regression_with_binning':  # Note: for now, binning based on whole dataset, not just training set
        data, bin_predictions, regression_data = data
        args.bin_predictions = bin_predictions
        train_data, _, _ = split_data(data, args, sizes=args.split_sizes, seed=args.seed)
    else:
        if args.separate_test_set:
            train_data, _, _ = split_data(data, args, sizes=(0.8, 0.2, 0.0), seed=args.seed)
        else:
            train_data, _, _ = split_data(data, args, sizes=args.split_sizes, seed=args.seed)
    args.num_tasks = data.num_tasks()

    if args.dataset_type == 'regression':
        scaler = StandardScaler().fit(train_data.targets())
    else:
        scaler = None

    # Build model
    model = build_model(args)

    # Update checkpoints
    for checkpoint_path in args.checkpoint_paths:
        state_dict = torch.load(checkpoint_path)
        model.load_state_dict(state_dict)
        save_checkpoint(model, scaler, args, checkpoint_path)


if __name__ == '__main__':
    # Need args to match training settings
    # Need to include: --data_path, --dataset_type, --checkpoint_dir
    args = parse_train_args()
    update_old_checkpoint(args)
