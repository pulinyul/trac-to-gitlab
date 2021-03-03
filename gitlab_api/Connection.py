# vim: autoindent tabstop=4 shiftwidth=4 expandtab softtabstop=4 filetype=python fileencoding=utf-8
'''
Copyright © 2013 
    Eric van der Vlist <vdv@dyomedea.com>
    Jens Neuhalfen <http://www.neuhalfen.name/>
See license information at the bottom of this file
'''

import json
import requests
import datetime
import hashlib

# See http://code.activestate.com/recipes/52308-the-simple-but-handy-collector-of-a-bunch-of-named/?in=user-97991
class Bunch(object):
    def __init__(self, **kwds):
        self.__dict__.update(kwds)

    @staticmethod
    def create(dictionary):
        if not dictionary:
            return None
        bunch = Bunch()
        bunch.__dict__ = dictionary
        return bunch

class Issues(Bunch):
    pass

class Notes(Bunch):
    pass

class Milestones(Bunch):
    pass

class Connection(object):
    """
    Connection to the gitlab API
    """

    def __init__(self, url, access_token, ssl_verify):
        """

        :param url: "https://www.neuhalfen.name/gitlab/api/v3"
        :param access_token: "secretsecretsecret"
        """
        self.url = url
        self.access_token = access_token
        self.verify = ssl_verify
        self.impers_tokens = dict()  #TODO would be nice to delete these tokens when finished
        self.user_ids = dict()  # username to user_id mapping
        self.uploaded_files = dict() # md5-hash to upload-file response (dict)

    def milestone_by_name(self, project_id, milestone_name):
        milestones = self.get("/projects/:project_id/milestones",project_id=project_id)
        for milestone in milestones:
            if milestone['title'] == milestone_name:
                return milestone

    def get_user_id(self, username):
        users = self.get("/users")
        for user in users:
            if user['username'] == username:
                return user["id"]
	return None

    def project_by_name(self, project_name):
        projects = self.get("/projects")
        for project in projects:
            if project['path_with_namespace'] == project_name:
                return project

    def get(self, url_postfix, **keywords):
        return self._get(url_postfix, keywords)

    def _request_headers(self, keywords) :
        headers = dict()
        if 'token' in keywords :
            headers['PRIVATE-TOKEN'] = keywords['token']
        else :
            headers['PRIVATE-TOKEN'] = self.access_token
        return headers

    def _get(self, url_postfix, keywords):
        """
        :param url_postfix: e.g. "/projects/:id/issues"
        :param keywords:  map, e.g. { "id" : 5 }
        :return: json of GET
        """
        completed_url = self._complete_url(url_postfix, keywords)+"&per_page=50"
        r = requests.get(completed_url, verify=self.verify)
        json = r.json()
        return json

    def put(self, url_postfix, data, **keywords):
        completed_url = self._complete_url(url_postfix, keywords)
        r = requests.put(completed_url,data= data, verify=self.verify)
        j = r.json()
        return j

    def post(self, url_postfix, data, **keywords):
        completed_url = self._complete_url(url_postfix, keywords)
        files = keywords['files'] if 'files' in keywords else None
        while True :
            r = requests.post(completed_url, data = data, verify = self.verify, files = files)
            if r.status_code < 500 :
                break
            time.sleep(2)
        if r.status_code >= 400 : print(r.text)
        r.raise_for_status()
        j = r.json() if r.status_code >= 200 and r.status_code < 300 else None
        return j

    def put_json(self, url_postfix, data, **keywords):
        completed_url = self._complete_url(url_postfix, keywords)
        payload = json.dumps(data)
        r = requests.put(completed_url, data= payload, verify=self.verify)
        j = r.json()
        return j

    def post_json(self, url_postfix, data, **keywords):
        completed_url = self._complete_url(url_postfix, keywords)
        payload = json.dumps(data)
        headers = self._request_headers(keywords)
#	data['PRIVATE-TOKEN'] = headers['PRIVATE-TOKEN']
        r = requests.post(completed_url, data=data, verify=self.verify)
	print("Posting to %s"%r.url)
	print("with header %s"%headers)
	print("data: %s"%data)
        j = r.json()
	print("Reply: %s"%j)
        return j

    def delete(self, url_postfix, **keywords):
	completed_url = self._complete_url(url_postfix, keywords)
#	payload = json.dumps(data)
	headers = self._request_headers(keywords)
	r = requests.delete(completed_url, headers=headers, verify=self.verify)
	j = r.text
	return j

    def create_issue(self, dest_project_id, new_issue):
        if hasattr(new_issue, 'milestone'):
            new_issue.milestone_id = new_issue.milestone
        if hasattr(new_issue, 'assignee'):
            new_issue.assignee_id = new_issue.assignee
        if hasattr(new_issue, 'author'):
#            author = new_issue.author
	    #also delete dictionary entry
	    userid = new_issue.author
#	    print("author assigned: ", author)
#	    userid = self.get_user_id(author)
	    print("user id: %s" % userid)
	    delattr(new_issue,'author')
            token = self.get_user_imperstoken(userid)
	    print(userid, " impersonation token acquired: ", token)
        else:
            token = self.access_token
	    print("Using default token: ", token)

        new_ticket = self.post_json("/projects/:id/issues",new_issue.__dict__, id=dest_project_id, token=token)
        new_ticket_id  = new_issue.iid
        # setting closed in create does not work -- limitation in gitlab
        if new_issue.state == 'closed': self.close_issue(dest_project_id,new_ticket_id)
        return Issues.create(new_ticket)

    def create_milestone(self, dest_project_id, new_milestone):
        if hasattr(new_milestone, 'due_date'):
            new_milestone.due_date = new_milestone.due_date.isoformat()
        existing = Milestones.create(self.milestone_by_name(dest_project_id, new_milestone.title))
        if existing:
            new_milestone.id = existing.id
            return Milestones.create(self.put("/projects/:id/milestones/:milestone_id", new_milestone.__dict__, id=dest_project_id, milestone_id=existing.id))
        else:
            return Milestones.create(self.post_json("/projects/:id/milestones", new_milestone.__dict__, id=dest_project_id))

    def create_wiki(self, dest_project_id, content, title, author):
        token = self.get_user_imperstoken(author)
        new_wiki_data = {
            "id" : dest_project_id,
            "content" : content,
            "title" : title
        }
        self.post("/projects/:project_id/wikis", new_wiki_data, project_id = dest_project_id, token = token)

    def comment_issue(self ,project_id, ticket, note, binary_attachment):
        if hasattr(note, 'attachment_name') :
           # ensure file name will be in ascii (otherwise gitlab complain)
           origname = note.attachment_name
           note.attachment_name = note.attachment_name.encode("ascii", "replace")
           r = self.upload_file(project_id, note.author, note.attachment_name, binary_attachment)
           relative_path_start_index = r['markdown'].index('/')
           #relative_path = r['markdown'][:relative_path_start_index] + '..' + r['markdown'][relative_path_start_index:]
           relative_path = r['markdown']
           note.note = "Attachment added: " + relative_path + '\n\n' + note.note
           if origname != note.attachment_name :
               note.note += '\nFilename changed during trac to gitlab conversion. Original filename: ' + origname

	userid = note.author
	token = self.get_user_imperstoken(userid)
        new_note_data = {
            "id" : project_id,
            "issue_id" :ticket.iid,
            "body" : note.note,
	    "created_at" : note.created_at
        }
        self.post_json( "/projects/:project_id/issues/:issue_id/notes", new_note_data, project_id=project_id, issue_id=ticket.iid, token=token)

    def get_user_imperstoken(self, userid) :
        if userid in self.impers_tokens :
            return self.impers_tokens[userid];
        data = {
            'user_id' : userid,
            'name' : 'trac2gitlab',
            'expires_at' : (datetime.date.today() + datetime.timedelta(days = 1)).strftime('%Y-%m-%dT%H:%M:%S.%f'),
            'scopes[]' : 'api'
            }
	print(json.dumps(data))
        r = self.post_json('/users/:user_id/impersonation_tokens', data, user_id = userid)
	print json.dumps(r)
        self.impers_tokens[userid] = r['token'];
        return r['token']

    def upload_file(self, project_id, author, filename, filedata) :
        token = self.get_user_imperstoken(author)

        h = hashlib.md5(filename + filedata).hexdigest()
        if h in self.uploaded_files :
            print '  use previous upload of file', filename
            return self.uploaded_files[h]

        print '  upload file', filename, ' author: ', author, 'token: ', token
        r = self.post("/projects/:project_id/uploads", None, files = {'file' : (filename, filedata)}, project_id = project_id, token = token)
        self.uploaded_files[h] = r;
        return r

    def close_issue(self,project_id,ticket_id):
        new_note_data = {"state_event": "close"}
        self.put("/projects/:project_id/issues/:issue_id", new_note_data, project_id=project_id, issue_id=ticket_id)

    def clear_issues(self, project_id):
	url_postfix = "/projects/:project_id/issues"
	keywords = {'project_id':project_id}
	completed_url = self._complete_url(url_postfix, keywords)+"&per_page=50"
        r = requests.get(completed_url, verify=self.verify)
#        issues_page = r.json()
#        return json
#	issues_page = self.get("/projects/:project_id/issues",project_id=project_id)
	pagesStr = r.headers['x-total-pages']
	pages = int(pagesStr)
	print("Deleting existing issues on pages:", pagesStr, " ", pages)
	for page in range(pages):
		issues_page = self.get("/projects/:project_id/issues",project_id=project_id,page=page)
		for issue in issues_page:
			issue_iid = issue["iid"]
			r = self.delete("/projects/:id/issues/:issue_iid", id=project_id, issue_iid=issue_iid)
			print "Deleted issue: ", issue_iid, " Response: ", r
	print "Deleting all issues finished"

    def _complete_url(self, url_postfix, keywords):
        url_postfix_with_params = self._url_postfix_with_params(url_postfix, keywords)
	if 'token' in keywords:
	    #complete_url = "%s%s" % (self.url, url_postfix_with_params)
	    complete_url = "%s%s?private_token=%s" % (self.url, url_postfix_with_params, keywords['token'])
	else:
	    complete_url = "%s%s?private_token=%s" % (self.url, url_postfix_with_params, self.access_token)
        return complete_url

    def _url_postfix_with_params(self, url_postfix, keywords):
        """

        :param url_postfix:  "/projects/:id/issues"
        :param keywords:  map, e.g. { "id" : 5 }
        :return:  "/projects/5/issues"
        """

        result = url_postfix
        for key, value in keywords.items():
            k = ":" + str(key)
            v = str(value)
            result = result.replace(k, v)
        return result

'''
This file is part of <https://gitlab.dyomedea.com/vdv/trac-to-gitlab>.

This sotfware is free software: you can redistribute it and/or modify
it under the terms of the GNU Lesser General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This sotfware is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
GNU Lesser General Public License for more details.

You should have received a copy of the GNU Lesser General Public License
along with this library. If not, see <http://www.gnu.org/licenses/>.
'''
