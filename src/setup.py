import os
from setuptools import setup, find_packages

version_file = os.path.join(os.path.dirname(__file__), "leetveld", "version.txt")

__version__ = open(version_file).read().strip()

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


