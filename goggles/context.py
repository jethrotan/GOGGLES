import json
import os
import torch

from types import SimpleNamespace
from goggles.constants import *
from goggles.models.semantic_ae import SemanticAutoencoder
from goggles.opts import DATASET_MAP, DATA_DIR_MAP


def load_context_from_run_id(run_id):
    """
    :param run_id: int
    :return: context: SimpleNamespace
    """
    with open(os.path.join(ALL_RUNS_DIR, str(run_id), 'config.json'), 'r') as read_file:
        config = json.load(read_file)

    input_image_size = config['input_image_size']
    patch_size = config['patch_size']
    dataset = config['dataset']
    filter_class_ids = config['filter_class_ids']

    Dataset = DATASET_MAP[dataset]
    data_dir = DATA_DIR_MAP[dataset]
    _, train_dataset, test_dataset = \
        Dataset.load_dataset_splits(
            data_dir, input_image_size,
            filter_class_ids)

    model = SemanticAutoencoder(
        input_image_size, patch_size,
        train_dataset.num_attributes)

    model.load_weights(os.path.join(ALL_RUNS_DIR, str(run_id), MODEL_FILE_NAME))
    if torch.cuda.is_available():
        model.cuda()

    dataset = SimpleNamespace(train=train_dataset, test=test_dataset)
    context = SimpleNamespace(model=model, dataset=dataset, config=config)
    return context