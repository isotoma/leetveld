from setuptools import setup, find_packages

__version__ = open('codereview/version.txt').read()

setup(
    name='leetveld',
    version=__version__,
    packages=find_packages(),
    zip_safe=False,
    include_package_data=True,
    entry_points={
        'console_scripts': [
            'importer = scripts.import_users:main'
        ]
    }
)


