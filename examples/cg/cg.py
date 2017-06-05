import argparse
import contextlib
import time

import numpy as np
from scipy.sparse.linalg import cg
from scipy.sparse import rand
import six

import cupy


@contextlib.contextmanager
def timer(message):
    cupy.cuda.Stream.null.synchronize()
    start = time.time()
    yield
    cupy.cuda.Stream.null.synchronize()
    end = time.time()
    print('%s:  %f sec' % (message, end - start))


def fit(A, b, x0, tol, max_iter):
    xp = cupy.get_array_module(A)
    x = x0
    r0 = b - xp.dot(A, x)
    p = r0
    for i in six.moves.range(max_iter):
        a = xp.dot(r0.T, r0) / xp.dot(xp.dot(p.T, A), p)
        x = x + p * a
        r1 = r0 - xp.dot(A * a, p)
        if xp.linalg.norm(r1) < tol:
            return x
        b = xp.dot(r1.T, r1) / xp.dot(r0.T, r0)
        p = r1 + b * p
        r0 = r1
    msg = 'Failed to converge. Increase max-iter or tol.'
    print(msg)
    return x


def run(gpuid, tol, max_iter):
    # Solve simultaneous linear equations, Ax = b.
    for repeat in range(1):
        print("Trial: %d" % repeat)
        # create the large sparse symmetric matrix 'A'.
        N = 2000
        max_val = 50
        density = 0.3
        A = rand(N, N, density / 2).A
        ran = np.random.randint(max_val, size=(N, N))
        A *= ran
        A = (A + A.T).astype(np.int32)
        b = rand(1, N, density).A.reshape((N),)
        ran = np.random.randint(max_val, size=N)
        b *= ran
        b = b.astype(np.int32)
        x0 = np.zeros(N, dtype=np.int32)

        msg = 'b[:20]='
        print(msg)
        print(b[:20])

        with timer(' CPU '):
            x = fit(A, b, x0, tol, max_iter)
            b_calc = np.dot(A, x)
            print(np.rint(b_calc[:20]).astype(np.int32))

        with cupy.cuda.Device(gpuid):
            A_gpu = cupy.asarray(A)
            b_gpu = cupy.asarray(b)
            x0_gpu = cupy.asarray(x0)
            with timer(' GPU '):
                x = fit(A_gpu, b_gpu, x0_gpu, tol, max_iter)
                b_calc = cupy.dot(A_gpu, x)
                print(cupy.rint(b_calc[:20]).astype(np.int32))

        with timer(' SciPy '):
            x = cg(A, b)
            b_calc = np.dot(A, x[0])
            print(np.rint(b_calc[:20]).astype(np.int32))

        print()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--gpu-id', '-g', default=0, type=int,
                        help='ID of GPU.')
    parser.add_argument('--tol', '-t', default=5.0, type=float,
                        help='tolerance to stop iteration')
    parser.add_argument('--max-iter', '-m', default=5000, type=int,
                        help='number of iterations')
    args = parser.parse_args()
    run(args.gpu_id, args.tol, args.max_iter)
