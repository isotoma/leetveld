from setuptools import setup, find_packages

version = '0.11.1dev'

def long_description():
    def file_or_emptystring(filename):
        contents = ''
        try:
            this_file = open(filename, 'r')
            contents = this_file.read()
            this_file.close()
        except IOError:
            pass

        return contents

    return '%s\n\n%s' % (
        file_or_emptystring('../README.rst'),
        file_or_emptystring('../CHANGES.rst')
    )

setup(
    name='leetveld',
    description='A ready-to-deploy gae2django version of rietveld',
    long_description=long_description(),
    version=version,
    packages=find_packages(),
    zip_safe=False,
    include_package_data=True,
    install_requires = [
        'django-gae2django==0.1-03e4e6',
    ],
)
