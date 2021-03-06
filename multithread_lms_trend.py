from __future__ import print_function
import numpy as np
root = '/mnt/disk1/dat/lchen63/grid/data/'
import cPickle as pickle
from multiprocessing import Pool
import os

regions_root = '/mnt/disk1/dat/lchen63/grid/data/lms/'


def worker(video_name):
    folder_path = regions_root + video_name
    if not os.path.exists(folder_path):
        print('folder not exists: {}'.format(folder_path))
        return video_name, None
    
    previous = None
    tt = []
    for i in range(1, 76):
        cur_fname = os.path.join(folder_path, video_name + '_%03d.npy' % i)
        if not os.path.exists(cur_fname):
            print('path not exists: {}'.format(cur_fname))
            return video_name, None
        try:
            cur = np.load(cur_fname)
        except:
            print('load file failed: {}'.format(cur_fname))
            return video_name, None
        if np.any(np.isinf(cur)):
            print('has inf: {}'.format(video_name))
            return video_name, None

        if previous is not None:
            value = np.mean(cur - previous)
            tt.append(value)
        
        previous = cur

    print(video_name)
    assert len(tt) > 0
    return video_name, tt
    			
    	
if __name__ == '__main__':
    video_names = os.listdir('/mnt/disk1/dat/lchen63/grid/data/regions/')

    pool = Pool(40)
    result = pool.map(worker, video_names)

    result = dict([(vname, tt)
                    for (vname, tt) in result if tt is not None and len(tt) > 0])

    with open('/mnt/disk0/dat/zhiheng/lip_movements/grid_trend_lms.pkl', 'wb') as handle:
        pickle.dump(result, handle)
