import numpy as np
from numpy.linalg import norm
from scipy.optimize import linprog
from scipy.linalg import solve
from time import time

import fileio, results

def l1_min(A, b, method='interior-point'):
    assert A.ndim == 2 and b.ndim == 1
    m, n = A.shape
    I = np.identity(m)
    A_lb = np.block([[-A, I], [A, I]])
    b_lb = np.block([-b, b])
    c = np.block([np.zeros(n), np.ones(m)])
    print(A_lb.shape, b_lb.shape, c.shape)
    start_time = time()
    res = linprog(
        c, A_ub=-A_lb, b_ub=-b_lb, bounds=(None, None),
        options={"maxiter": np.inf, "tol": 1e-7}, method=method
    )
    time_taken = time() - start_time
    print("{} Function value is {:.8g} after {} iterations in {:.4g} s".format(
        res.message, res.fun, res.nit, time_taken
    ))
    return res.x[:n], time_taken, res.status

def linf_min(A, b, method='interior-point'):
    assert A.ndim == 2 and b.ndim == 1
    m, n = A.shape
    ones = np.ones([m, m])
    A_lb = np.block([[-A, ones], [A, ones]])
    b_lb = np.block([-b, b])
    c = np.block([np.zeros(n), np.ones(m)])
    print(A_lb.shape, b_lb.shape, c.shape)
    start_time = time()
    res = linprog(
        c, A_ub=-A_lb, b_ub=-b_lb, bounds=(None, None),
        options={"maxiter": np.inf, "tol": 1e-7}, method=method
    )
    time_taken = time() - start_time
    print("{} Function value is {:.8g} after {} iterations in {:.4g} s".format(
        res.message, res.fun, res.nit, time_taken
    ))
    return res.x[:n], time_taken, res.success

def l2_min(A, b):
    assert A.ndim == 2 and b.ndim == 1
    n = A.shape[1]
    start_time = time()
    x, residual, rank, _ = np.linalg.lstsq(A, b, rcond=None)
    time_taken = time() - start_time
    print("Residual is {:.8g}, rank is {}, time taken is {:.4g} s".format(
        *residual, rank, time_taken
    ))
    return x[:n], time_taken, rank

def analyse_methods(
    problem_list=range(1, 6), num_attempts=3, max_simplex_n=256,
    folder=results.DEFAULT_FOLDER, filename_prefix="results_problem_"
):
    """Analyse methods of norm-minimisation for different methods.

    One `.npz` results file is saved for each problem, containing 2
    `np.ndarray`s, 1 named `x_vals` and 1 named `t_vals`.

    `x_vals` contains 3 rows, which respectively contain the solution-vector
    found by minimising:
     - The l2 norm
     - The l1 norm
     - The linfinity norm
    
    `t_vals` contains either 3 or 5 rows, which respectively contain the times
    taken for differet attempts at minimisation using:
     - Least squares and the l2 norm
     - Interior point methods and the l1 norm
     - Interior point methods and the linfinity norm
     - [Simplex and the l1 norm]
     - [Simplex and the linfinity norm]
    """
    start_time = time()
    for problem in problem_list:
        A, b = fileio.load_A_b(problem)
        n = A.shape[1]
        x_vals = np.empty([3, n])
        if n <= max_simplex_n: t_vals = np.empty([5, num_attempts])
        else: t_vals = np.empty([3, num_attempts])
        for attempt in range(num_attempts):
            # Calculate solutions and time taken for interior-point and LS
            x_vals[0], t_vals[0, attempt], _ = l2_min(A, b)
            x_vals[1], t_vals[1, attempt], _ = l1_min(
                A, b, method='interior-point'
            )
            x_vals[2], t_vals[2, attempt], _ = linf_min(
                A, b, method='interior-point'
            )
            # For small problems, calculate time taken for the simplex method
            if n <= max_simplex_n:
                _, t_vals[3, attempt], _ = l1_min(
                    A, b, method='simplex'
                )
                _, t_vals[4, attempt], _ = linf_min(
                    A, b, method='simplex'
                )
        # Save results for each problem in a `.npz` file
        np.savez(
            folder + filename_prefix + str(problem),
            x_vals=x_vals, t_vals=t_vals
        )
    time_taken = time() - start_time
    if time_taken > 60:
        m, s = divmod(time_taken, 60)
        print("All problems analysed in {}m {}s".format(m, s))
    else: print("All problems analysed in {:.4g}s".format(time_taken))

def smooth_l1(A, x, b, epsilon):
    Axb = A.dot(x) - b
    return np.sqrt(Axb ** 2 + epsilon ** 2).sum()

def smooth_l1_gradient(A, x, b, epsilon):
    Axb = A.dot(x) - b
    u = Axb / np.sqrt(Axb ** 2 + epsilon ** 2)
    return A.T.dot(u)

def smooth_l1_hessian(A, x, b, epsilon):
    Axb = A.dot(x) - b
    Lambda = (epsilon ** 2) / (np.sqrt(Axb ** 2 + epsilon ** 2) ** 3)
    return A.T.dot(Lambda.reshape(-1, 1) * A)

def smooth_l1_backtrack_condition(A, x, b, epsilon, t, delta, alpha, grad):
    old_val = smooth_l1(A, x, b, epsilon)
    new_val = smooth_l1(A, x + t * delta, b, epsilon)
    min_decrease = -alpha * t * grad.dot(delta)

    return old_val - new_val > min_decrease

def display_backtracking_progress(
    outer_step, inner_step, grad, A, x, b, epsilon
):
    print(
        "Outer = {}, inner = {},".format(outer_step, inner_step),
        "norm(grad) = {:.4}, func = {:.10}".format(
            norm(grad), smooth_l1(A, x, b, epsilon)
        )
    )

def min_smooth_l1_backtracking(
    A, b, epsilon=0.01, t0=1e-2, alpha=0.5, beta=0.5, grad_tol=1e-3,
    random_init=False
):
    n = A.shape[1]
    if random_init: x = np.random.normal(size=n)
    else: x = np.zeros(shape=n)
    grad = smooth_l1_gradient(A, x, b, epsilon)
    outer_step = 0
    while norm(grad) >= grad_tol:
        t = t0
        inner_step = 0
        while not smooth_l1_backtrack_condition(
            A, x, b, epsilon, t, -grad, alpha, grad
        ):
            t = beta * t
            inner_step += 1
        x = x - t * grad
        grad = smooth_l1_gradient(A, x, b, epsilon)
        display_backtracking_progress(
            outer_step, inner_step, grad, A, x, b, epsilon
        )
        outer_step += 1
    return x


def min_smooth_l1_forward_backtracking(
    A, b, epsilon=0.01, t0=1e-2, alpha=0.5, beta=0.5, grad_tol=1e-3,
    random_init=False
):
    n = A.shape[1]
    if random_init: x = np.random.normal(size=n)
    else: x = np.zeros(shape=n)
    grad = smooth_l1_gradient(A, x, b, epsilon)
    outer_step = 0
    t = t0
    while norm(grad) >= grad_tol:
        inner_step = 0
        if not smooth_l1_backtrack_condition(
            A, x, b, epsilon, t, -grad, alpha, grad
        ):
            while not smooth_l1_backtrack_condition(
                A, x, b, epsilon, t, -grad, alpha, grad
            ):
                t = beta * t
                inner_step += 1
        else:
            while smooth_l1_backtrack_condition(
                A, x, b, epsilon, t, -grad, alpha, grad
            ):
                t = t / beta
                inner_step += 1
            t = beta * t
            
        x = x - t * grad
        grad = smooth_l1_gradient(A, x, b, epsilon)
        display_backtracking_progress(
            outer_step, inner_step, grad, A, x, b, epsilon
        )
        outer_step += 1
    return x

def min_smooth_l1_newton(
    A, b, epsilon=0.01, t0=1e-2, alpha=0.5, beta=0.5, grad_tol=1e-3,
    random_init=False
):
    n = A.shape[1]
    if random_init: x = np.random.normal(size=n)
    else: x = np.zeros(shape=n)
    grad = smooth_l1_gradient(A, x, b, epsilon)
    outer_step = 0
    while norm(grad) >= grad_tol:
        hess = smooth_l1_hessian(A, x, b, epsilon)
        v = -solve(hess, grad, assume_a="pos", check_finite=False)
        t = t0
        inner_step = 0
        while not smooth_l1_backtrack_condition(
            A, x, b, epsilon, t, v, alpha, grad
        ):
            t = beta * t
            inner_step += 1
        x = x + t * v

        grad = smooth_l1_gradient(A, x, b, epsilon)
        display_backtracking_progress(
            outer_step, inner_step, grad, A, x, b, epsilon
        )
        outer_step += 1
    return x

if __name__ == "__main__":
    A, b = fileio.load_A_b(5)
    # print(A.shape, b.shape)
    # x, _, _ = l1_min(A, b, method='interior-point')
    # x, _, _ = linf_min(A, b, method='interior-point')
    # x, _, _ = l2_min(A, b)
    # print(x.shape)
    # print("{:.4}".format(norm(x, 1)))
    # analyse_methods(
    #     problem_list=[1, 2, 3], max_simplex_n=0, filename_prefix='test'
    # )
    # analyse_methods()
    # min_smooth_l1_backtracking(A, b)
    # min_smooth_l1_forward_backtracking(A, b)
    # min_smooth_l1_backtracking(A, b, beta=0.1)
    # min_smooth_l1_backtracking(A, b, t0=1e-3, alpha=0.9)
    min_smooth_l1_newton(A, b, t0=1.0)
    # min_smooth_l1_newton(A, b, random_init=True)
