from setuptools import setup, find_packages

setup(
    name='leetveld',
    version='0.7',
    packages=find_packages(),
    zip_safe=False,
    include_package_data=True,
    entry_points={
        'console_scripts': [
            'importer = scripts.import_users:main'
        ]
    }
)


