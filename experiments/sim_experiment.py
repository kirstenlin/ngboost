import pandas as pd
import scipy as sp
import scipy.stats
from scipy.stats import norm
from sklearn.tree import DecisionTreeRegressor
from torch.distributions.log_normal import LogNormal

from ngboost import SurvNGBoost
from ngboost.scores import *
from experiments.evaluation import *


def create_cov_matrix(num_vars, cov_strength):
    '''
    Generate the covariate matrix for normally distributed covariates
    '''
    cov = np.zeros((num_vars, num_vars), dtype=float)
    for i, j in np.ndindex(cov.shape):
        cov[i, j] = cov_strength[i] * cov_strength[j]
        cov[range(num_vars), range(num_vars)] = 1
    return cov

def simulate_X(num_normal=5, normal_cov_strength=[0.1,0.3,0.8,0.9,0.5], num_unif=1, num_bi=2, N=10):
    '''

    '''
    cov_normal = create_cov_matrix(num_normal, normal_cov_strength)
    X = sp.stats.multivariate_normal.rvs(cov=cov_normal, size=N)
    for i in range(num_unif):
        X_uniform = sp.stats.uniform.rvs(loc=0, scale=1, size=N)
        X = np.hstack((X, [[a] for a in X_uniform]))
    for i in range(num_bi):
        X_bino = np.random.binomial(1, 0.5, size=N)
        X = np.hstack((X, [[a] for a in X_bino]))
    return X

'''
A set of functions for parameters
'''
def f_const(X, const):
    '''
    A contant function of X. 
    '''
    return [const] * len(X)

def f_linear(X, coef):
    '''
    A linear function of X.
    coef :: a list of coefficients for covariates of X
    '''
    return np.sum(coef * X, axis=1)

def f_linear_exp(X, coef):
    '''
    A linear exponential function of X. Note that might need to adjust expectation.
    coef :: a list of coefficients for covariates of X
    '''
    return np.sum(coef ** X, axis=1)

def f_custom(X):
    '''
    A non-linear non-monotonic fucntion of X.
    '''
    pnorm = norm.cdf
    res = 4 * (X[:,0] > 1) * (X[:,1] > 0) + 4 * (X[:,2] > 1) * (X[:,3] > 0) + \
            2 * X[:,4] * X[:,0] - 4 * pnorm(-1) #adjust expectation
    return res

def simulate_Y_C(X, D = sp.stats.lognorm, D_config={'s':1, 'scale':1, 'loc':0}):

    ''' 
    Input:
    D :: conditional outcome distribtuion, can choose from sp.stats.genextreme, sp.stats.lognorm, and etc
    D_config :: parameters of the distribution, each can be generated by a customized function,
                such as f_const, f_linear, f_linear_exp, f_custom
    
    Returns: (Y, X)
    '''
    
    n_observations = len(X)
    D_s = abs(f_custom(X))
    D_loc = f_const(X, 1.5)
    D_config['s'] = D_s
    D_config['loc'] = D_loc
    T = D.rvs(s=D_config['s'], scale=D_config['scale'], loc=D_config['loc'], size=n_observations)
    U = D.rvs(s=1, scale=1, loc=0, size=n_observations)
    Y = np.minimum(T, U)
    C = (T > U) * 1.0
    return Y, C

def create_df(X, Y, C, num):
    df = pd.DataFrame(X, columns=["X%d" % i for i in range(X.shape[1])])
    df["Y"] = Y
    df["C"] = C
    df = df.sample(frac=1, replace=False)
    train_file = 'data/simulated/sim_data_train_' + str(num) + '.csv'
    test_file = 'data/simulated/sim_data_test_' + str(num) + '.csv'
    df.iloc[:700].to_csv(train_file, index=False)
    df.iloc[700:].to_csv(test_file, index=False)


def run_experiments(df_train_filename, df_test_filename, natural_gradient = False,
                   second_order = False, quadrant_search = False):
    df_train = pd.read_csv(df_train_filename)
    df_test = pd.read_csv(df_test_filename)
    Y = np.array(df_train['Y'])
    C = np.array(df_train['C'])
    X = np.array(df_train.drop(['Y', 'C'], axis=1))
    sb = SurvNGBoost(Base = lambda : DecisionTreeRegressor(criterion='mse'),
                     Dist = LogNormal,
                     Score = CRPS_surv,
                     n_estimators = 1000,
                     learning_rate = 0.1,
                     natural_gradient = natural_gradient,
                     second_order = second_order,
                     quadrant_search = quadrant_search,
                     nu_penalty=1e-5)
    loss_train = sb.fit(X, Y, C)
    
    preds_train = sb.pred_mean(X)
    preds_test = sb.pred_mean(df_test.drop(["Y", "C"], axis=1))
    conc_test = calculate_concordance_naive(preds_test, df_test["Y"], df_test["C"])
    test_true_mean = np.mean(df_test["Y"])
    test_pred_mean = np.mean(preds_test)
    return loss_train, conc_test, test_true_mean, test_pred_mean
