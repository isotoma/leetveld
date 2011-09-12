# -*- coding: utf-8 -*-

"""Setup script for django-gae2django."""

import os

from distutils.core import setup


def find_packages(base_dir):
    yield base_dir
    for fname in os.listdir(base_dir):
        if fname.startswith('.'):
            continue
        fullpath = os.path.join(base_dir, fname)
        if os.path.isdir(fullpath):
            for item in find_packages(fullpath):
                yield item


setup(
    name='django-gae2django',
    version='0.1',
    description='Django-based implementation of App Engine APIs',
    author='Andi Albrecht',
    author_email='albrecht.andi@gmail.com',
    url='http://code.google.com/p/django-gae2django/',
    packages=list(find_packages('gae2django')),
    license='Apache',
    classifiers=[
        'Development Status :: 4 - Beta',
        'Environment :: Web Environment',
        'Framework :: Django',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: Apache Software License',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Programming Language :: Python :: 2.5',
        'Programming Language :: Python :: 2.6',
        ],
)

