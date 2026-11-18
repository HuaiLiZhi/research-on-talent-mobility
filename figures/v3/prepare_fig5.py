"""Prepare combined-direction means and international-share stratification."""
from prepare_fig5_combined import prepare
from prepare_fig5_stratified import prepare as prepare_stratified

if __name__ == '__main__':
    prepare()
    prepare_stratified()
