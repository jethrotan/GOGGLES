from collections import defaultdict

import numpy as np
import torch
import torch.nn as nn

from encoder import Encoder
from decoder import Decoder
from patch import Patch
from prototype import Prototypes


class SemanticAutoencoder(nn.Module):
    def __init__(self, input_size, encoded_patch_size, num_prototypes):
        super(SemanticAutoencoder, self).__init__()
        self._is_cuda = False

        self.input_size = input_size
        self.encoded_patch_size = encoded_patch_size
        self.num_prototypes = num_prototypes

        self._encoder_net = Encoder(input_size)
        self._decoder_net = Decoder(self._encoder_net.num_out_channels)

        encoded_output_size = self._encoder_net.output_size
        assert encoded_patch_size <= encoded_output_size
        self._patches = Patch.from_spec(
            (encoded_output_size, encoded_output_size),
            (encoded_patch_size, encoded_patch_size))

        self._receptive_fields_for_patches = dict()

        dim_prototypes = self._encoder_net.num_out_channels * (encoded_patch_size ** 2)
        self.prototypes = Prototypes(num_prototypes + 1, dim_prototypes, padding_idx=0)
        self.prototypes.weight.requires_grad = False  # freeze embeddings

    def _make_cuda(self, x):
        return x.cuda() if self._is_cuda else x

    def forward(self, x):
        z = self._encoder_net(x)
        reconstructed_x = self._decoder_net(z)

        z_patches = [patch(z) for patch in self._patches]  # [patch1:Tensor(batch_size, dim), patch2, ...]
        z_patches = torch.stack(z_patches)  # num_patches, batch_size, embedding_dim
        z_patches = z_patches.transpose(0, 1)  # batch_size, num_patches, embedding_dim

        return z, z_patches, reconstructed_x

    def cuda(self, device_id=None):
        self._is_cuda = True
        return super(SemanticAutoencoder, self).cuda(device_id)

    def get_receptive_field_for_patch(self, patch_idx):
        if patch_idx not in self._receptive_fields_for_patches:
            self.zero_grad()

            image_size = self.input_size
            batch_shape = (1, 3, image_size, image_size)

            x = self._make_cuda(torch.autograd.Variable(
                torch.rand(*batch_shape), requires_grad=True))
            z = self._encoder_net.forward(x)
            z_patch = self._patches[patch_idx].forward(z)

            torch.sum(z_patch).backward()

            rf = x.grad.data.cpu().numpy()
            rf = rf[0, 0]
            rf = zip(*np.where(np.abs(rf) > 1e-6))

            (i_nw, j_nw), (i_se, j_se) = rf[0], rf[-1]

            rf_w, rf_h = (j_se - j_nw + 1,
                          i_se - i_nw + 1)

            self._receptive_fields_for_patches[patch_idx] = \
                (i_nw, j_nw), (rf_w, rf_h)

            self.zero_grad()

        return self._receptive_fields_for_patches[patch_idx]

    def get_nearest_patches_for_prototypes(self, dataset):
        all_patches = list()
        all_patch_id_indices = dict()
        candidate_patch_indices_dict = defaultdict(list)

        for i, (image, _, attributes, num_nonzero_attributes) in enumerate(dataset):
            x = image.view((1,) + image.size())
            x = self._make_cuda(torch.autograd.Variable(x))
            z, z_patches, reconstructed_x = self.forward(x)

            attributes = attributes[:num_nonzero_attributes]

            patches = z_patches[0]
            for j, patch in enumerate(patches):
                patch_id = (i, j)
                for prototype_idx in attributes:
                    candidate_patch_indices_dict[prototype_idx].append(patch_id)

                # store the index where patch will be added in all_patches
                all_patch_id_indices[patch_id] = len(all_patches)
                all_patches.append(patch.data.cpu().numpy())

        nearest_patches_for_prototypes = dict()
        for k in range(1, self.num_prototypes + 1):
            candidate_patches = list()
            for patch_id in candidate_patch_indices_dict[k]:
                i_ = all_patch_id_indices[patch_id]
                candidate_patches.append(all_patches[i_])
            candidate_patches = np.array(candidate_patches)

            prototype = self.prototypes.weight[k].data.cpu().numpy()
            dists = np.linalg.norm(prototype - candidate_patches, ord=2, axis=1)

            nearest_patch_idx = np.argmin(dists)
            nearest_patch = torch.FloatTensor(candidate_patches[nearest_patch_idx])
            nearest_image_patch_idx = candidate_patch_indices_dict[k][nearest_patch_idx]  # (image_idx, patch_idx)
            nearest_patches_for_prototypes[k] = (nearest_image_patch_idx, nearest_patch)

        return nearest_patches_for_prototypes

    def reproject_prototypes(self, nearest_patches_for_prototypes):
        for k, (nearest_image_patch_idx, nearest_patch) \
                in nearest_patches_for_prototypes.items():
            self.prototypes.weight[k].data = nearest_patch


if __name__ == '__main__':
    from itertools import ifilter
    input_image_size = 64
    expected_image_shape = (3, input_image_size, input_image_size)
    input_tensor = torch.autograd.Variable(torch.rand(5, *expected_image_shape))

    net = SemanticAutoencoder(input_image_size, 1, 10)
    # print net.state_dict()
    # for p in ifilter(lambda p: p.requires_grad, net.parameters()):
    #     print p.size()
    # print
    # z, z_patches, reconstructed_x = net(input_tensor)
    # print z.size()
    # print reconstructed_x.size()
    # print z_patches[0].size()
    # print len(z_patches)

    # print net.prototypes.weight[1]

    print net.get_receptive_field_for_patch(0)
