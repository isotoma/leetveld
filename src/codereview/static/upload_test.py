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
        self.RunShell = upload.RunShell
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
        self.os_path = upload.os.path
        self.unified_diff = upload.unified_diff
        self.get_empty_file_path = upload.get_empty_file_path

        self.svn = upload.SubversionVCS(options)

    def test_GenerateDiff_with_revision(self):
        def RunShell(cmd):
            if cmd[:2] == ['svn', 'diff']:
                return test_svn_diff
        upload.RunShell = RunShell

        self.assertEqual(self.svn.GenerateDiff([]), test_svn_diff)

    def test_GenerateDiff_with_args(self):
        def RunShell(cmd):
            if cmd[:2] == ['svn', 'diff']:
                return test_svn_diff
        upload.RunShell = RunShell
        self.svn.options.revision = None

        self.assertEqual(self.svn.GenerateDiff(['args']), test_svn_diff)

    def test_GenerateDiff(self):
        def RunShell(cmd):
            if cmd[:2] == ['svn', 'diff']:
                return test_svn_diff
            if cmd[:2] == ['svn', 'status']:
                return test_svn_status
        upload.RunShell = RunShell

        class OsPath(object):
            def isfile(self, path):
                return '.' in path
        upload.os.path = OsPath()
        self.svn.options.revision = None

        def unified_diff(empty_file, path):
            return 'unified_diff output %s\n' % path
        upload.unified_diff = unified_diff
        upload.get_empty_file_path = lambda: '/dev/null'

        self.assertEqual(self.svn.GenerateDiff([]), (
            '%sIndex: src/settings/social_networks.py\n'
            '%s\n'
            'unified_diff output src/settings/social_networks.py\n'
            % (test_svn_diff, '=' * 67)))

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
        upload.RunShell = self.RunShell
        upload.SubversionVCS.GetRepoPath = self.GetRepoPath
        upload.os.path = self.os_path
        upload.unified_diff = self.unified_diff
        upload.get_empty_file_path = self.get_empty_file_path


test_svn_status = '''<?xml version="1.0"?>
<status>
<target
   path=".">
<entry
   path="upload.sh">
<wc-status
   props="none"
   item="unversioned">
</wc-status>
</entry>
<entry
   path="iso">
<wc-status
   props="none"
   item="external">
</wc-status>
</entry>
<entry
   path="src/settings">
<wc-status
   props="none"
   copied="true"
   item="added">
</wc-status>
</entry>
<entry
   path="src/settings/social_networks.py">
<wc-status
   props="none"
   copied="true"
   item="added">
<commit
   revision="21232">
<author>richard</author>
<date>2010-09-17T09:51:14.205447Z</date>
</commit>
</wc-status>
</entry>
<entry
   path="src/settings/__init__.py">
<wc-status
   props="none"
   copied="true"
   item="added">
<commit
   revision="21232">
<author>richard</author>
<date>2010-09-17T09:51:14.205447Z</date>
</commit>
</wc-status>
</entry>
<entry
   path="templates/control_panel.pt">
<wc-status
   props="none"
   item="modified"
   revision="21279">
<commit
   revision="19858">
<author>matt</author>
<date>2010-08-24T10:39:15.897599Z</date>
</commit>
</wc-status>
</entry>
<entry
   path="manage_abc.py">
<wc-status
   props="none"
   item="deleted"
   revision="21279">
<commit
   revision="19858">
<author>matt</author>
<date>2010-08-24T10:39:15.897599Z</date>
</commit>
</wc-status>
</entry>
</target>
</status>
'''

test_svn_diff = '''Index: src/settings/__init__.py
===================================================================
--- src/settings/__init__.py       (revision 21232)
+++ src/settings/__init__.py       (working copy)
@@ -9,4 +9,5 @@
 __docformat__ = 'restructuredtext en'
 __version__ = '$Revision$'[11:-2]

-import social_networks
\ No newline at end of file
+import social_networks
+#abc
Index: manage_abc.py
===================================================================
--- manage_abc.py        (revision 21279)
+++ manage_abc.py        (working copy)
@@ -1,30 +0,0 @@
-# Header
-# comments
-print 'abc'
Index: templates/control_panel.pt
===================================================================
--- templates/control_panel.pt  (revision 21279)
+++ templates/control_panel.pt  (working copy)
@@ -45,10 +45,6 @@

       <h2>Manage</h2>
       <p>The messages displayed to users leaving the site</p>
-
-      <h2>Manage other stuff</h2>
-      <p>Choose which options should be available</p>
-
       <div>
         <h2>...</h2>
         <div>
'''

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
