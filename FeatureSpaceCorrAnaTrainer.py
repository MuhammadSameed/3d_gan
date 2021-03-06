import os
import time
import torch
import torch.utils
import torch.nn as nn
import torchvision
from torch.autograd import Variable
from torch.utils.data import DataLoader
from corr_ana_autoencoder import AudioDerivativeAutoEncoder, FlowAutoEncoder
import itertools



class Trainer():
    def __init__(self, config):
        self.mse_loss_fn = nn.MSELoss()
        self.audio_deri_autoencoder = AudioDerivativeAutoEncoder()
        self.flow_autoencoder = FlowAutoEncoder()

        self.opt_g = torch.optim.Adam(itertools.chain(self.audio_deri_autoencoder.parameters(),
                                                      self.flow_autoencoder.parameters()),
                                      lr=config.lr, betas=(config.beta1, config.beta2))

        ########multiple GPU####################
        if config.cuda:
            device_ids = [int(i) for i in config.device_ids.split(',')]
            self.generator = nn.DataParallel(self.generator.cuda(), device_ids=device_ids)
            self.discriminator = nn.DataParallel(self.discriminator.cuda(), device_ids=device_ids)
            self.bce_loss_fn = self.bce_loss_fn.cuda()
            self.mse_loss_fn = self.mse_loss_fn.cuda()
            self.ones = self.ones.cuda()
            self.zeros = self.zeros.cuda()

        self.config = config
        self.start_epoch = 0
        if config.load_model:
            self.start_epoch = config.start_epoch
            self.load(config.pretrained_dir, config.pretrained_epoch)

        assert config.dataset != 'lrw', 'only GRID available'

        self.data_loader = DataLoader(self.dataset,
                                      batch_size=config.batch_size,
                                      num_workers=config.num_thread,
                                      pin_memory=True,
                                      shuffle=True, drop_last=True)

    def fit(self):
        config = self.config

        num_steps_per_epoch = len(self.data_loader)
        cc = 0
        config.perceptual = False

        for epoch in range(self.start_epoch, config.max_epochs):
            for step, (example_image, example_lms, right_imgs, right_lmss, wrong_imgs, wrong_lmss) in enumerate(
                    self.data_loader):
                t1 = time.time()

                if config.cuda:
                    example_image = Variable(example_image).cuda()
                    right_lmss = Variable(right_lmss).cuda()
                    right_imgs = Variable(right_imgs).cuda()
                    wrong_lmss = Variable(wrong_lmss).cuda()

                else:
                    example_image = Variable(example_image)
                    right_lmss = Variable(right_lmss)
                    right_imgs = Variable(right_imgs)
                    wrong_lmss = Variable(wrong_lmss)

                fake_im = self.generator(example_image, right_lmss)
                real_im = right_imgs

                # train the discriminator

                D_real = self.discriminator(example_image, real_im, right_lmss)

                D_wrong = self.discriminator(
                    example_image, real_im, wrong_lmss)

                D_fake = self.discriminator(
                    example_image, fake_im.detach(), right_lmss)

                loss_real = self.bce_loss_fn(D_real, self.ones)
                loss_wrong = self.bce_loss_fn(D_wrong, self.zeros)
                loss_fake = self.bce_loss_fn(D_fake, self.zeros)

                loss_disc = loss_real + 0.5 * (loss_wrong + loss_fake)
                loss_disc.backward()
                self.opt_d.step()
                self._reset_gradients()

                # train the generator
                fake_im = self.generator(example_image, right_lmss)
                D_fake = self.discriminator(example_image, fake_im, right_lmss)

                loss_gen = self.bce_loss_fn(D_fake, self.ones)
                loss = loss_gen
                loss.backward()
                self.opt_g.step()
                self._reset_gradients()

                t2 = time.time()

                if (step + 1) % 10 == 0 or (step + 1) == num_steps_per_epoch:
                    steps_remain = num_steps_per_epoch - step + 1 + \
                                   (config.max_epochs - epoch + 1) * num_steps_per_epoch
                    eta = int((t2 - t1) * steps_remain)
                    # if config.perceptual:
                    #     print("[{}/{}][{}/{}]   Loss_G: {:.4f}, loss_perceptual: {:.4f}  ETA: {} second"
                    #           .format(epoch+1, config.max_epochs,
                    #                   step+1, num_steps_per_epoch, loss_gen.data[0], loss_perc.data[0],  eta))
                    #     log_value('generator_loss',loss_gen.data[0] , step + num_steps_per_epoch * epoch)
                    # else:

                    print("[{}/{}][{}/{}]   Loss_G: {:.4f}, Loss_D: {:.4f},  ETA: {} second"
                          .format(epoch + 1, config.max_epochs,
                                  step + 1, num_steps_per_epoch, loss_gen.data[0], loss_disc.data[0], eta))
                if (step) % (num_steps_per_epoch / 50) == 0:
                    fake_store = fake_im.data.permute(0, 2, 1, 3, 4).contiguous().view(
                        config.batch_size * 16, 3, 64, 64)
                    torchvision.utils.save_image(fake_store,
                                                 "{}fake_{}.png".format(config.sample_dir, cc), nrow=16, normalize=True)
                    real_store = right_imgs.data.permute(0, 2, 1, 3, 4).contiguous().view(
                        config.batch_size * 16, 3, 64, 64)
                    torchvision.utils.save_image(real_store,
                                                 "{}real_{}.png".format(config.sample_dir, cc), nrow=16, normalize=True)
                    cc += 1

                    torch.save(self.generator.state_dict(),
                               "{}/generator_{}.pth"
                               .format(config.model_dir, cc))
                    torch.save(self.discriminator.state_dict(),
                               "{}/discriminator_{}.pth"
                               .format(config.model_dir, cc))

    def load(self, directory, epoch):
        gen_path = os.path.join(directory, 'generator_{}.pth'.format(epoch))

        self.generator.load_state_dict(torch.load(gen_path))

        dis_path = os.path.join(
            directory, 'discriminator_{}.pth'.format(epoch))

        self.discriminator.load_state_dict(torch.load(dis_path))

        print("Load pretrained [{}, {}]".format(gen_path, dis_path))

    def _reset_gradients(self):
        self.generator.zero_grad()
        self.discriminator.zero_grad()


import argparse


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--lr",
                        type=float,
                        default=0.0002)
    parser.add_argument("--beta1",
                        type=float,
                        default=0.5)
    parser.add_argument("--beta2",
                        type=float,
                        default=0.999)
    parser.add_argument("--lambda1",
                        type=int,
                        default=10)
    parser.add_argument("--batch_size",
                        type=int,
                        default=32)
    parser.add_argument("--noise_size",
                        type=int,
                        default=0)
    parser.add_argument("--max_epochs",
                        type=int,
                        default=5)
    parser.add_argument("--cuda",
                        default=True)
    parser.add_argument("--dataset_dir",
                        type=str,
                        default="/mnt/disk1/dat/lchen63/lrw/data/pickle/")
    # default = '/media/lele/DATA/lrw/data2/pickle')
    parser.add_argument("--model_dir",
                        type=str,
                        default="/mnt/disk1/dat/lchen63/lrw/model/3d_warp")
    # default='/media/lele/DATA/lrw/data2/model')
    parser.add_argument("--sample_dir",
                        type=str,
                        default="/mnt/disk1/dat/lchen63/lrw/sample/3d_warp/")
    # default='/media/lele/DATA/lrw/data2/sample/lstm_gan')
    parser.add_argument("--log_dir",
                        type=str,
                        default="/mnt/disk1/dat/lchen63/data/lrw/data/log/")
    # default="/media/lele/DATA/lrw/data2/log/lstm_gan/")
    parser.add_argument('--device_ids', type=str, default='0,1')
    parser.add_argument('--dataset', type=str, default='lrw')
    parser.add_argument('--num_thread', type=int, default=32)
    # parser.add_argument('--flownet_pth', type=str, help='path of flownets model')
    parser.add_argument('--weight_decay', type=float, default=4e-4)
    parser.add_argument('--lr_corr', type=float, default=0.0001)
    parser.add_argument('--lr_flownet', type=float, default=1e-4)
    parser.add_argument('--fake_corr', type=bool, default=True)
    parser.add_argument('--load_model', action='store_true')
    parser.add_argument('--pretrained_dir', type=str)
    parser.add_argument('--pretrained_epoch', type=int)
    parser.add_argument('--start_epoch', type=int,
                        default=0, help='start from 0')
    parser.add_argument('--perceptual', type=bool, default=False)

    return parser.parse_args()


def main(config):
    t = Trainer(config)
    t.fit()


if __name__ == "__main__":
    config = parse_args()
    config.is_train = 'train'
    if not os.path.exists(config.model_dir):
        os.mkdir(config.model_dir)
    if not os.path.exists(config.sample_dir):
        os.mkdir(config.sample_dir)

    main(config)
