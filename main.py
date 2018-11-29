from config import Arg

args = Arg()
import tensorflow as tf

tf.enable_eager_execution()

from os import path, system
from dataset import CelebA
from utils import save_image
from model import Adjuster, Discriminator, Decoder, Encoder, Generator
from eager_trainer import EagerTrainer
from git import Repo
import time
import numpy as np

decoder = Decoder(args)
encoder = Encoder(args)
generator = Generator(args, decoder)
discriminator = Discriminator(args, encoder)
adjuster = Adjuster(args, encoder, decoder)

print("Application Params: ", args, "\r\n")
print("Using GPUs: ", args.gpu)

data = CelebA(args)
print("\r\nImage Flows From: ", args.image_path, "   Image Count: ", args.batch_size * data.batches)
print("\r\nUsing Attribute: ", data.label)

model = EagerTrainer(args, generator, discriminator, adjuster, data)

if args.mode == "train":
    repo = Repo(".")
    if repo.is_dirty() and not args.debug:  # 程序被修改且不是测试模式
        raise EnvironmentError("Git repo is Dirty! Please train after committed.")
    model.train()
elif args.mode == "visual":  # loss etc的可视化
    print("The result path is ", path.join(args.result_dir, "log"))
    system("tensorboard --host 0.0.0.0 --logdir " + path.join(args.result_dir, "log"))
elif args.mode == "plot":
    model.plot()  # 输出模型结构图
elif args.mode == "random-sample":
    iterator = data.get_new_iterator()
    now_time = int(time.time())
    for b in range(args.random_sample_batch):
        image, cond = iterator.get_next()
        noise = tf.random_uniform([cond.shape[0], args.noise_dim])

        model.predict(noise, cond, image,
                      path.join(args.result_dir, "sample", "generator-%s-%d.jpg" % (now_time, b)),
                      path.join(args.result_dir, "sample", "discriminator-%s-%d.json" % (now_time, b)),
                      path.join(args.result_dir, "sample", "adjuster-%s-%d.jpg" % (now_time, b))
                      )
        np.savez_compressed(path.join(args.result_dir, "sample", "input_data-%s-%d.npz" % (now_time, b)), n=noise, c=cond, i=image)
elif args.mode == "evaluate":
    iterator = data.get_new_iterator()
    progress = tf.keras.utils.Progbar(args.evaluate_sample_batch * args.batch_size)
    for b in range(args.evaluate_sample_batch):
        base_index = b * args.batch_size + 1
        image, cond = iterator.get_next()
        noise = tf.random_uniform([cond.shape[0], args.noise_dim])
        gen_image, save, adj_real_image, adj_fake_image = model.predict(noise, cond, image,
                                                                        None, path.join(args.result_dir, "evaluate", "discriminator.json"), None)
        for i in range(args.batch_size):
            save_image(gen_image[i], path.join(args.result_dir, "evaluate", "gen", str(base_index + i) + ".jpg"))
            if adj_real_image is not None and adj_fake_image is not None:
                save_image(adj_real_image[i], path.join(args.result_dir, "evaluate", "adj", "real_" + str(base_index + i) + ".jpg"))
                save_image(adj_fake_image[i], path.join(args.result_dir, "evaluate", "adj", "fake_" + str(base_index + i) + ".jpg"))
        progress.add(args.batch_size)

    if not args.gpu:
        args.gpu = [-1]

    gen_cmd = "python evaluate.py calc %s %s %s %s --gpu %s" % (
        path.join(args.result_dir, "evaluate", "gen"),
        path.join(args.test_data_dir, args.evaluate_pre_calculated),
        args.test_data_dir,
        ",".join(map(str, args.gpu)),
        path.join(args.result_dir, "evaluate", "fid-gen.log")
    )

    print("Running: \"", gen_cmd, "\"")
    system(gen_cmd)
    if args.train_adj:
        adj_cmd = "python evaluate.py calc %s %s %s %s --gpu %s" % (
            path.join(args.result_dir, "evaluate", "adj"),
            path.join(args.test_data_dir, args.evaluate_pre_calculated),
            args.test_data_dir,
            ",".join(map(str, args.gpu)),
            path.join(args.result_dir, "evaluate", "fid-adj.log")
        )
        print("Running: \"", adj_cmd, "\"")
        system(adj_cmd)
elif args.mode == "condition-sample":
    bar = tf.keras.utils.Progbar(args.condition_sample_batch)
    for i in range(1, 1 + args.condition_sample_batch):
        cond = tf.keras.utils.to_categorical(range(args.cond_dim), args.cond_dim) * 0.88 + 0.04
        noise = np.random.uniform(size=[1, args.noise_dim]).astype(np.float32)
        noise = np.repeat(noise, args.cond_dim, 0)
        img = model.generator([noise, cond])
        # img2 = img[[x for x in range(7) if x % 7 in [0, 3, 4, 5]]]
        save_image(img, path.join(args.result_dir, "sample", "condition-gen-%d.jpg" % i), (1, args.cond_dim))
        bar.add(1)


else:
    print("没有此模式：", args.mode)
