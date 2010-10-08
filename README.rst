===================
README for leetveld
===================

Buildout setup
++++++++++++++

::

    git clone git@github.com:isotoma/leetveld.git
    cd leetveld
    ./configure
    python bootstrap.py --distribute
    bin/buildout

Initial setup
+++++++++++++

::

    bin/django syncdb

Run the server
++++++++++++++

::

    bin/django runserver

Testing dev version of upload.py
++++++++++++++++++++++++++++++++

::

    ln -s ~/bin/leetload_dev ~/projects/leetveld/src/codereview/static/upload.py
    chmod +x ~/bin/leetload_dev

Then call with the server arg

::

    leetload_dev --server=http://localhost:8000 -r foo@isotoma.com


