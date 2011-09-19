===================
README for leetveld
===================

What is Leetveld?
=================

Leetveld is the "rietveld" django app-engine project converted to vanilla django
with the assistance of the django-gaedjango app and the rietveld_helper app,
the first of which pretends to be google.appengine.api and google.appengine.ext
by taking standard django objects, such as django.contrib.auth.models and makes
them appear to be their app-engine equivalents.

The rietveld-helper app, which comes with django-gae2django then does the rest
of the work, plugging the project-level gaps with a coherent url configuration
and some common utilities.

Aside from this, we've applied a number of patches to get the /admin back-end
working nicely, and to ensure that users must be logged in to view any code of
any kind.

Finally, the entire bundle has been productionised meaning that you can fairly
effortlessly deploy this software.

Versions
========

rietveld = 6bbee3d7523b...
gae2django = 03e4e6...

Usage
=====

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


