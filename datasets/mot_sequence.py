import configparser
import csv
import os
import os.path as osp

import numpy as np
import torch
from PIL import Image
from torch.utils.data import Dataset
from torchvision.transforms import ToTensor
import datasets.transforms as T
import json
import random
import cv2


class MOTSequence(Dataset):
    """Multiple Object Tracking Dataset.

    This dataloader is designed so that it can handle only one sequence, if more have to be
    handled one should inherit from this class.
    """

    def __init__(self, seq_name, mot_dir, vis_threshold=0.0):
        """
        Args:
            seq_name (string): Sequence to take
            vis_threshold (float): Threshold of visibility of persons above which they are selected
        """
        self._seq_name = seq_name
        self._vis_threshold = vis_threshold

        self._mot_dir = mot_dir

        self._train_folders = os.listdir(os.path.join(self._mot_dir, 'gmot'))
        self._test_folders = os.listdir(os.path.join(self._mot_dir, 'gmot'))
        # self._train_folders = os.listdir(os.path.join(self._mot_dir, 'image'))
        # self._test_folders = os.listdir(os.path.join(self._mot_dir, 'image'))

        self.transforms = ToTensor()
        assert seq_name in self._train_folders + self._test_folders, \
            'Image set does not exist: {}'.format(seq_name)

        self.data, self.no_gt, self.template, self.image_wh = self._sequence()

    def __len__(self):
        return len(self.data)

    def __getitem__(self, idx):
        """Return the ith image converted to blob"""
        data = self.data[idx]
        img = Image.open(data['im_path']).convert("RGB")
        img = self.transforms(img)

        sample = {}
        sample['img'] = img
        sample['dets'] = torch.tensor([det[:4] for det in data['dets']])
        sample['img_path'] = data['im_path']
        sample['gt'] = data['gt']
        sample['vis'] = data['vis']

        return sample

    def _sequence(self):
        seq_name = self._seq_name
        if seq_name in self._train_folders:
            seq_path = osp.join(self._mot_dir, 'gmot', seq_name)
            # seq_path = osp.join(self._mot_dir, 'image', seq_name)
        else:
            seq_path = osp.join(self._mot_dir, 'gmot', seq_name)
            # seq_path = osp.join(self._mot_dir, 'image', seq_name)

        config_file = osp.join(seq_path, 'seqinfo.ini')
        # config_file = osp.join(self._mot_dir, 'seq_info/{}_seqinfo.ini'.format(seq_name))

        assert osp.exists(config_file), \
            'Config file does not exist: {}'.format(config_file)

        config = configparser.ConfigParser()
        config.read(config_file)
        seqLength = int(config['Sequence']['seqLength'])
        # startframe = int(config['Sequence']['startframe'])
        w = int(config['Sequence']['imWidth'])
        h = int(config['Sequence']['imHeight'])
        imDir = config['Sequence']['imDir']

        imDir = osp.join(seq_path, imDir) # gmot
        # imDir = osp.join(seq_path)

        gt_file = osp.join(self._mot_dir, 'annotations', 'gmot_test.json')
        # gt_file = osp.join(self._mot_dir, 'annotations', 'urban_track_det_gt.json')
        # with open(gt_file) as info:
        #     gt = json.load(info)
        # images = gt['images']
        # annotations = gt['annotations']
        # template_image_name = 'gmot/' + self._seq_name + '/img1/000000.jpg'
        # image_id = next(x for x in images if x["file_name"] == template_image_name)['id']
        # template_annos = list(filter(lambda item: item['image_id'] == image_id, annotations))
        # template_anno = random.choices(template_annos)
        
        # template_img_path = osp.join(self._mot_dir, template_image_name)
        # img = Image.open(template_img_path).convert("RGB")
        # # import pdb; pdb.set_trace()
        # w, h = img.size
        # image_size = [w, h]
        # box = template_anno[0]['bbox']
        # box[2] += box[0]
        # box[3] += box[1]
        # template = img.crop(box)
        # template_path = 'track_vis/template/template_' + self._seq_name + '.jpg'
        # template.save(template_path)
        # template = Image.open('template/gmot_track/' + seq_name + '.jpg')
        # template = Image.open('template/gmot2/' + seq_name + '.jpg')
        image_size = [w, h]
        template = Image.open('template/gmot_track/' + seq_name + '.jpg')
        template, _ = T.resize(template, target=None, size=400, max_size=400)
        tran_template = T.Compose([ 
            T.ToTensor(),
            T.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
        ])
        template, _ = tran_template(template, target=None)
        # vis template feature
        # from torchvision import transforms
        # unloader = transforms.ToPILImage()
        # image = template.cpu().clone()  # clone the tensor
        # image = image.squeeze(0)  # remove the fake batch dimension
        # image = unloader(image)
        # name = 'track_vis/example_' + self._seq_name + '.jpg'
        # image.save(name)

        gt_file = osp.join(seq_path, 'gt', 'gt.txt')

        total = []

        visibility = {}
        boxes = {}
        dets = {}

        for i in range(0, seqLength+1):
            boxes[i] = {}
            visibility[i] = {}
            dets[i] = []

        no_gt = False
        if osp.exists(gt_file):
            with open(gt_file, "r") as inf:
                reader = csv.reader(inf, delimiter=',')
                for row in reader:
                    # class person, certainity 1, visibility >= 0.25
                    if int(row[6]) == 1 and int(row[7]) == 1 and float(row[8]) >= self._vis_threshold:
                        # Make pixel indexes 0-based, should already be 0-based (or not)
                        x1 = int(row[2]) - 1
                        y1 = int(row[3]) - 1
                        # This -1 accounts for the width (width of 1 x1=x2)
                        x2 = x1 + int(row[4]) - 1
                        y2 = y1 + int(row[5]) - 1
                        bb = np.array([x1,y1,x2,y2], dtype=np.float32)
                        boxes[int(row[0])][int(row[1])] = bb
                        visibility[int(row[0])][int(row[1])] = float(row[8])
        else:
            no_gt = True

        det_file = osp.join(seq_path, 'det', 'det.txt')

        if osp.exists(det_file):
            with open(det_file, "r") as inf:
                reader = csv.reader(inf, delimiter=',')
                for row in reader:
                    x1 = float(row[2]) - 1
                    y1 = float(row[3]) - 1
                    # This -1 accounts for the width (width of 1 x1=x2)
                    x2 = x1 + float(row[4]) - 1
                    y2 = y1 + float(row[5]) - 1
                    score = float(row[6])
                    bb = np.array([x1,y1,x2,y2, score], dtype=np.float32)
                    dets[int(float(row[0]))].append(bb)

        # for i in range(0, seqLength):
            # im_path = osp.join(imDir, f"{i+startframe:08d}.jpg")
        for i in range(0, seqLength+1):
            im_path = osp.join(imDir, f"{i:06d}.jpg")
            sample = {'gt':boxes[i],
                      'im_path':im_path,
                      'vis':visibility[i],
                      'dets':dets[i],}

            total.append(sample)

        return total, no_gt, template, image_size

    def __str__(self):
        return self._seq_name

    def write_results(self, all_tracks, output_dir):
        """Write the tracks in the format for MOT16/MOT17 sumbission

        all_tracks: dictionary with 1 dictionary for every track with {..., i:np.array([x1,y1,x2,y2]), ...} at key track_num

        Each file contains these lines:
        <frame>, <id>, <bb_left>, <bb_top>, <bb_width>, <bb_height>, <conf>, <x>, <y>, <z>
        """

        #format_str = "{}, -1, {}, {}, {}, {}, {}, -1, -1, -1"

        if not os.path.exists(output_dir):
            os.makedirs(output_dir)

        with open(osp.join(output_dir, f"{self._seq_name}.txt"), "w") as of:
            writer = csv.writer(of, delimiter=',')
            for i, track in all_tracks.items():
                for frame, bb in track.items():
                    x1 = bb[0]
                    y1 = bb[1]
                    x2 = bb[2]
                    y2 = bb[3]
                    writer.writerow(
                        [frame + 1,
                         i + 1,
                         x1 + 1,
                         y1 + 1,
                         x2 - x1 + 1,
                         y2 - y1 + 1,
                         -1, -1, -1, -1])

    def load_results(self, output_dir):
        file_path = osp.join(output_dir, self._seq_name)
        results = {}

        if not os.path.isfile(file_path):
            return results

        with open(file_path, "r") as of:
            csv_reader = csv.reader(of, delimiter=',')
            for row in csv_reader:
                frame_id, track_id = int(row[0]) - 1, int(row[1]) - 1

                if not track_id in results:
                    results[track_id] = {}

                x1 = float(row[2]) - 1
                y1 = float(row[3]) - 1
                x2 = float(row[4]) - 1 + x1
                y2 = float(row[5]) - 1 + y1

                results[track_id][frame_id] = [x1, y1, x2, y2]

        return results


class MOTSequenceAttentionVisualization(MOTSequence):
    def _sequence(self):
        seq_name = self._seq_name
        if seq_name in self._train_folders:
            seq_path = osp.join(self._mot_dir, 'gmot', seq_name)
        else:
            seq_path = osp.join(self._mot_dir, 'gmot', seq_name)

        config_file = osp.join(seq_path, 'seqinfo.ini')

        assert osp.exists(config_file), \
            'Config file does not exist: {}'.format(config_file)

        config = configparser.ConfigParser()
        config.read(config_file)
        seqLength = int(config['Sequence']['seqLength'])
        imDir = config['Sequence']['imDir']

        imDir = osp.join(seq_path, imDir)

        
        img_path = os.path.join(self._mot_dir, 'gmot', self._seq_name, 'img1', '000000.jpg')
        img = Image.open(img_path).convert("RGB")
        # # import pdb; pdb.set_trace()
        w, h = img.size
        image_size = [w, h]

        template = Image.open(osp.join(self._mot_dir, 'template', seq_name + '.jpg'))
        print(osp.join(self._mot_dir, 'template', seq_name + '.jpg'))
        template, _ = T.resize(template, target=None, size=400, max_size=400)
        tran_template = T.Compose([ 
            T.ToTensor(),
            T.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
        ])
        template, _ = tran_template(template, target=None)

        gt_file = osp.join(seq_path, 'gt', 'gt.txt')

        total = []

        visibility = {}
        boxes = {}
        dets = {}

        for i in range(0, seqLength+1):
            boxes[i] = {}
            visibility[i] = {}
            dets[i] = []

        no_gt = False
        if osp.exists(gt_file):
            with open(gt_file, "r") as inf:
                reader = csv.reader(inf, delimiter=',')
                for row in reader:
                    # class person, certainity 1, visibility >= 0.25
                    if int(row[6]) == 1 and int(row[7]) == 1 and float(row[8]) >= self._vis_threshold:
                        # Make pixel indexes 0-based, should already be 0-based (or not)
                        x1 = int(row[2]) - 1
                        y1 = int(row[3]) - 1
                        # This -1 accounts for the width (width of 1 x1=x2)
                        x2 = x1 + int(row[4]) - 1
                        y2 = y1 + int(row[5]) - 1
                        bb = np.array([x1,y1,x2,y2], dtype=np.float32)
                        boxes[int(row[0])][int(row[1])] = bb
                        visibility[int(row[0])][int(row[1])] = float(row[8])
        else:
            no_gt = True

        det_file = osp.join(seq_path, 'det', 'det.txt')

        if osp.exists(det_file):
            with open(det_file, "r") as inf:
                reader = csv.reader(inf, delimiter=',')
                for row in reader:
                    x1 = float(row[2]) - 1
                    y1 = float(row[3]) - 1
                    # This -1 accounts for the width (width of 1 x1=x2)
                    x2 = x1 + float(row[4]) - 1
                    y2 = y1 + float(row[5]) - 1
                    score = float(row[6])
                    bb = np.array([x1,y1,x2,y2, score], dtype=np.float32)
                    dets[int(float(row[0]))].append(bb)

        for i in range(0, seqLength+1):
            im_path = osp.join(imDir, f"{i:06d}.jpg")

            sample = {'gt':boxes[i],
                      'im_path':im_path,
                      'vis':visibility[i],
                      'dets':dets[i],}

            total.append(sample)

        return total, no_gt, template, image_size