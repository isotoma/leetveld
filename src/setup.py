from setuptools import setup, find_packages

version = '0.11.0dev'

setup(
    name='leetveld',
    version=version,
    packages=find_packages(),
    zip_safe=False,
    include_package_data=True,
    install_requires = [
        'django-gae2django==0.1-03e4e6',
    ],
)
