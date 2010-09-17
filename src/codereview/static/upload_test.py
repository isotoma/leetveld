"""Tests for upload.py, the CLI tool which allows uploading a diff patch or set of patches, for review"""

import unittest

import upload

class testUploadDiff(unittest.TestCase):
    def setUp(self):
        pass
    
    """Test that if a file is submitted for its first review that it is uploaded in its entirety"""
    def testSingleFileNew(self):
        upload.main

    def tearDown(self):
        pass


class TestSubversionVCS(unittest.TestCase):
    def setUp(self):
        self.RunShellWithReturnCode = upload.RunShellWithReturnCode
        class Options(object):
            revision = None
            download_base = None
        options = Options()
        options.revision = '20702'

        self._GuessBase = upload.SubversionVCS._GuessBase
        def _GuessBase(*args):
            return 'https://svnserver/svn/branches/5983'
        upload.SubversionVCS._GuessBase = _GuessBase

        self.GetRepoPath = upload.SubversionVCS.GetRepoPath

        self.svn = upload.SubversionVCS(options)

    def test_GetRepoPath(self):
        def RunShellWithReturnCode(cmd):
            return test_svn_info, 0
        upload.RunShellWithReturnCode = RunShellWithReturnCode
        self.assertEqual(self.svn.GetRepoPath(), '/branches/5983')

    def GetStatusSetup(self):
        def GetRepoPath(self):
            return '/branches/5983'
        upload.SubversionVCS.GetRepoPath = GetRepoPath

    def test_GetStatus_with_revision_add_directory(self):
        """Test GetStatus returns the right status when a revision is
        given and the commit adds a directory
        """
        def RunShellWithReturnCode(cmd):
            return test_add_directory_log, 0
        upload.RunShellWithReturnCode = RunShellWithReturnCode
        self.GetStatusSetup()
        self.assertEqual(self.svn.GetStatus('tests/__init__.py'), 'A   ')

    def test_GetStatus_with_revision_modified(self):
        """Test GetStatus returns the right status when a revision
        is given and the commit modifies a file
        """
        def RunShellWithReturnCode(cmd):
            return test_modified_log, 0
        upload.RunShellWithReturnCode = RunShellWithReturnCode
        self.GetStatusSetup()
        self.assertEqual(self.svn.GetStatus('globals.py'), 'M   ')

    def test_GetStatus_with_revision_remove_directory(self):
        """Test GetStatus returns the right status when a revision
        is given and the commit removes a directory
        """
        def RunShellWithReturnCode(cmd):
            return test_remove_directory_log, 0
        upload.RunShellWithReturnCode = RunShellWithReturnCode
        self.GetStatusSetup()
        self.assertEqual(self.svn.GetStatus('trunk_7058'), 'D   ')

    def test_GetStatus_with_multiple_revisions(self):
        """Test GetStatus returns the right status when there are
        multiple revisions given.
        """
        def RunShellWithReturnCode(cmd):
            return test_multi_revision_log, 0
        upload.RunShellWithReturnCode = RunShellWithReturnCode
        self.GetStatusSetup()
        self.assertEqual(self.svn.GetStatus('globals.py'), 'A   ')
        self.assertEqual(self.svn.GetStatus('test.py'), 'D   ')
        self.assertEqual(self.svn.GetStatus('trunk_7058'), 'M   ')
        self.assertEqual(self.svn.GetStatus('__init__.py'), 'M   ')

    def tearDown(self):
        upload.SubversionVCS._GuessBase = self._GuessBase
        upload.RunShellWithReturnCode = self.RunShellWithReturnCode
        upload.SubversionVCS.GetRepoPath = self.GetRepoPath


test_svn_info = '''<?xml version="1.0"?>
<info>
<entry
   kind="dir"
   path="."
   revision="21243">
<url>https://svnserver/svn/branches/5983</url>
<repository>
<root>https://svnserver/svn</root>
<uuid>ea577d5f-ad40-4855-8eb6-2817e5ae8535</uuid>
</repository>
<wc-info>
<schedule>normal</schedule>
<depth>infinity</depth>
</wc-info>
<commit
   revision="20726">
<author>karen</author>
<date>2010-09-10T08:43:30.925428Z</date>
</commit>
</entry>
</info>
'''

test_add_directory_log = '''<?xml version="1.0"?>
<log>
<logentry
   revision="20703">
<author>karen</author>
<date>2010-09-09T10:49:09.384930Z</date>
<paths>
<path
   kind=""
   action="A">/branches/5983/tests/__init__.py</path>
<path
   kind=""
   action="A">/branches/5983/tests</path>
</paths>
<msg>#5983 Add tests
</msg>
</logentry>
</log>
'''

test_modified_log = '''<?xml version="1.0"?>
<log>
<logentry
   revision="20703">
<author>karen</author>
<date>2010-09-09T10:49:19.384930Z</date>
<paths>
<path
   kind=""
   action="M">/branches/5983/globals.py</path>
</paths>
<msg>#5983 Modify globals.py
</msg>
</logentry>
</log>
'''

test_remove_directory_log = '''<?xml version="1.0"?>
<log>
<logentry
   revision="7262">
<author>karen</author>
<date>2010-09-16T10:45:32.548616Z</date>
<paths>
<path
   kind=""
   action="D">/branches/5983/trunk_7058</path>
</paths>
<msg>testing
</msg>
</logentry>
</log>
'''

test_multi_revision_log = '''<?xml version="1.0"?>
<log>
<logentry
   revision="20701">
<author>karen</author>
<date>2010-09-16T10:45:32.548616Z</date>
<paths>
<path
   kind=""
   action="A">/branches/5983/globals.py</path>
<path
   kind=""
   action="M">/branches/5983/test.py</path>
<path
   kind=""
   action="D">/branches/5983/trunk_7058</path>
</paths>
<msg>testing
</msg>
</logentry>
<logentry
   revision="20702">
<author>karen</author>
<date>2010-09-09T10:49:19.384930Z</date>
<paths>
<path
   kind=""
   action="M">/branches/5983/globals.py</path>
</paths>
<msg>...
</msg>
</logentry>
<logentry
   revision="20703">
<author>karen</author>
<date>2010-09-09T10:49:19.384930Z</date>
<paths>
<path
   kind=""
   action="M">/branches/5983/__init__.py</path>
<path
   kind=""
   action="D">/branches/5983/test.py</path>
<path
   kind=""
   action="A">/branches/5983/trunk_7058</path>
</paths>
<msg>....
</msg>
</logentry>
</log>
'''

if __name__ == '__main__':
    unittest.main()
