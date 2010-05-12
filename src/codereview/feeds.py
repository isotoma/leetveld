# Copyright 2008 Google Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import datetime
import md5

from django.contrib.syndication.feeds import Feed
from django.core.exceptions import ObjectDoesNotExist
from django.utils.feedgenerator import Atom1Feed

import library
import models


class BaseFeed(Feed):
  title = 'Code Review'
  link = '/'
  description = 'Rietveld: Code Review Tool hosted on Google App Engine'
  feed_type = Atom1Feed

  def author_name(self):
    return 'rietveld'

  def item_guid(self, item):
    return 'urn:md5:%s' % (md5.new(str(item.key())).hexdigest())

  def item_link(self, item):
    if isinstance(item, models.PatchSet):
      if item.data is not None:
        return ('/download/issue%d_%d.diff' %
                (item.issue.key().id(), item.key().id()))
      else:
        # Patch set is too large, only the splitted diffs are available.
        return '/%s' % (item.parent_key().id())
    if isinstance(item, models.Message):
      return '/%s#msg-%s' % (item.issue.key().id(), item.key())
    return '/%s' % (item.key().id())

  def item_title(self, item):
    return 'the title'

  def item_author_name(self, item):
    if isinstance(item, models.Issue) or isinstance(item, models.PatchSet):
      return library.nickname(item.owner)
    if isinstance(item, models.Message):
      return library.nickname(item.sender)
    return 'Rietveld'

  def item_pubdate(self, item):
    if isinstance(item, models.Issue):
      return item.modified
    if isinstance(item, models.PatchSet):
      # Use created, not modified, so that commenting on
      # a patch set does not bump its place in the RSS feed.
      return item.created
    if isinstance(item, models.Message):
      return item.date
    return None


class BaseUserFeed(BaseFeed):

  def get_object(self, bits):
    """Returns the account for the requested user feed.

    bits is a list of URL path elements. The first element of this list
    should be the user's nickname. A 404 is raised if the list is empty or
    has more than one element or if the a user with that nickname
    doesn't exist.
    """
    if len(bits) != 1:
      raise ObjectDoesNotExist
    obj = bits[0]
    account = models.Account.get_account_for_nickname('%s' % obj)
    if account is None:
      raise ObjectDoesNotExist
    return account


class ReviewsFeed(BaseUserFeed):
  title = 'Code Review - All issues I have to review'

  def items(self, obj):
    return _rss_helper(obj.email, 'closed = FALSE AND reviewers = :1',
                       use_email=True)


class ClosedFeed(BaseUserFeed):
  title = "Code Review - Reviews closed by me"

  def items(self, obj):
    return _rss_helper(obj.email, 'closed = TRUE AND owner = :1')


class MineFeed(BaseUserFeed):
  title = 'Code Review - My issues'

  def items(self,obj):
    return _rss_helper(obj.email, 'closed = FALSE AND owner = :1')


class AllFeed(BaseFeed):
  title = 'Code Review - All issues'

  def items(self):
    query = models.Issue.gql('WHERE closed = FALSE AND private = FALSE '
                             'ORDER BY modified DESC')
    return query.fetch(RSS_LIMIT)


class OneIssueFeed(BaseFeed):
  title = 'Code Review'
  link = '/'

  def get_object(self, bits):
    if len(bits) != 1:
      raise ObjectDoesNotExist
    obj = models.Issue.get_by_id(int(bits[0]))
    if obj:
      return obj
    raise ObjectDoesNotExist

  def title(self, obj):
    return 'Code review - Issue %d: %s' % (obj.key().id(),obj.subject)

  def items(self, obj):
    all = list(obj.patchset_set) + list(obj.message_set)
    all.sort(key=self.item_pubdate)
    return all


### RSS feeds ###

# Maximum number of issues reported by RSS feeds
RSS_LIMIT = 20

def _rss_helper(email, query_string, use_email=False):
  account = models.Account.get_account_for_email(email)
  if account is None:
    issues = []
  else:
    query = models.Issue.gql('WHERE %s AND private = FALSE '
                             'ORDER BY modified DESC' % query_string,
                             use_email and account.email or account.user)
    issues = query.fetch(RSS_LIMIT)
  return issues
