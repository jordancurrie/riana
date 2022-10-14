# Riana.py - Relative Isotope Abundance Analyzer

Riana (Relative Isotope Abundance Analyzer) takes in standard mass spectrometry spectra and spectral ID files,
and returns mass isotopomer distributions, e.g., for protein turnover analysis.

Visit https://ed-lau.github.io/riana/ for Documentations and Usage.

## Installing RIANA

Install Python 3.7+ and pip. See instructions on Python website for specific instructions for your operating system.

Riana can be installed from PyPI via pip or directly from GitHub. We recommend using a virtual environment.

    $ pip install riana

Launch riana as a module (Usage/Help):
	
	$ python -m riana

Alternatively as a console entry point:

    $ riana
    
To test that the installation can load test data files in tests/data:

    $ pip install tox
    $ tox

To run the RIANA test dataset (a single fraction bovine serum albumin file from a Q-Exactive) and print the result
to the home directory:

    $ python -m riana integrate tests/data/sample1/ tests/data/sample1/percolator.target.psms.txt -q 0.1 -i 0,1,2,3,4,5 -o out/test/



### Dependencies

Riana.py is tested in Python 3.7, 3.8, 3.9 and uses the following packages:

```
matplotlib==3.4.1
pandas==1.2.4
pymzml==2.4.7
tqdm==4.60.0
scikit-learn==0.24.2
```


## Contributing

Please contact us if you wish to contribute, and submit pull requests to us.


## Authors

* **Edward Lau, PhD** - *Code/design* - [ed-lau](https://github.com/ed-lau)

See also the list of [contributors](https://github.com/Molecular-Proteomics/riana/graphs/contributors) who participated in this project.


## License

This project is licensed under the MIT License - see the [LICENSE.md](https://github.com/Molecular-Proteomics/riana/blob/master/LICENSE.md) file for details


