"""
© Copyright 2020 HP Development Company, L.P.
SPDX-License-Identifier: GPL-2.0-only
"""
import io
import json
import os
import re
import time

from git import Repo, Git, InvalidGitRepositoryError, GitError, PushInfo
from halo import Halo
from prettytable import PrettyTable

from ml_git import log
from ml_git.config import get_metadata_path
from ml_git.constants import METADATA_MANAGER_CLASS_NAME, HEAD_1, RGX_ADDED_FILES, RGX_DELETED_FILES, RGX_SIZE_FILES, \
    RGX_AMOUNT_FILES, TAG, AUTHOR, EMAIL, DATE, MESSAGE, ADDED, SIZE, AMOUNT, DELETED, SPEC_EXTENSION, \
    DEFAULT_BRANCH_FOR_EMPTY_REPOSITORY, PERFORMANCE_KEY, EntityType, FileType, RELATED_DATASET_TABLE_INFO, \
    RELATED_LABELS_TABLE_INFO, DATASET_SPEC_KEY, LABELS_SPEC_KEY
from ml_git.manifest import Manifest
from ml_git.ml_git_message import output_messages
from ml_git.spec import get_entity_dir, spec_parse, get_spec_key
from ml_git.utils import get_root_path, ensure_path_exists, yaml_load, RootPathException, get_yaml_str, yaml_load_str, \
    clear, posix_path, create_csv_file


class MetadataRepo(object):

    def __init__(self, git, path, repo_type):
        self.__repo_type = repo_type
        try:
            root_path = get_root_path()
            self.__path = os.path.join(root_path, path)
            self.__git = git
            ensure_path_exists(self.__path)
        except RootPathException as e:
            log.error(e, class_name=METADATA_MANAGER_CLASS_NAME)
            raise e
        except Exception as e:
            if str(e) == '\'Metadata\' object has no attribute \'_MetadataRepo__git\'':
                log.error(output_messages['ERROR_NOT_IN_RESPOSITORY'], class_name=METADATA_MANAGER_CLASS_NAME)
            else:
                log.error(e, class_name=METADATA_MANAGER_CLASS_NAME)
            return

    def init(self):
        try:
            log.info(output_messages['INFO_METADATA_INIT'] % (self.__git, self.__path), class_name=METADATA_MANAGER_CLASS_NAME)
            Repo.clone_from(self.__git, self.__path)
        except GitError as g:
            if 'fatal: repository \'\' does not exist' in g.stderr:
                raise GitError(output_messages['ERROR_UNABLE_TO_FIND_REMOTE_REPOSITORY'])
            elif 'Repository not found' in g.stderr:
                raise GitError(output_messages['ERROR_UNABLE_TO_FIND'] % self.__git)
            elif 'already exists and is not an empty directory' in g.stderr:
                raise GitError(output_messages['ERROR_PATH_ALREAD_EXISTS'] % self.__path)
            elif 'Authentication failed' in g.stderr:
                raise GitError(output_messages['ERROR_GIT_REMOTE_AUTHENTICATION_FAILED'])
            else:
                raise GitError(g.stderr)
            return

    def remote_set_url(self, mlgit_remote):
        try:
            if self.check_exists():
                repo = Repo(self.__path)
                repo.remote().set_url(new_url=mlgit_remote)
        except InvalidGitRepositoryError as e:
            log.error(e, class_name=METADATA_MANAGER_CLASS_NAME)
            raise e

    def check_exists(self):
        log.debug(output_messages['DEBUG_METADATA_CHECK_EXISTENCE'] % (self.__git, self.__path),
                  class_name=METADATA_MANAGER_CLASS_NAME)
        try:
            Repo(self.__path)
        except Exception:
            return False
        return True

    def checkout(self, sha=None):
        repo = Git(self.__path)
        if sha is None:
            sha = self.get_default_branch()
        repo.checkout(sha)

    def _get_symbolic_ref(self):
        repo = Repo(self.__path)
        for ref in repo.remotes.origin.refs:
            if ref.remote_head == 'HEAD':
                return ref.reference.name.replace('origin/', '')
        return None

    def _get_local_branch(self):
        repo = Repo(self.__path)
        format_output = '--format=%(refname:short)'
        iterate_limit = '--count=1'
        pattern = 'refs/heads'
        sort = '--sort=-*authordate'
        return repo.git.for_each_ref([format_output, pattern, sort, iterate_limit])

    def get_default_branch(self):
        remote_branch_name = self._get_symbolic_ref()
        local_branch_name = self._get_local_branch()

        if remote_branch_name:
            return remote_branch_name
        elif local_branch_name:
            return local_branch_name

        return DEFAULT_BRANCH_FOR_EMPTY_REPOSITORY

    def update(self):
        log.info(output_messages['INFO_MLGIT_PULL'] % self.__path, class_name=METADATA_MANAGER_CLASS_NAME)
        repo = Repo(self.__path)
        self.validate_blank_remote_url()
        o = repo.remotes.origin
        o.pull('--tags')

    def commit(self, file, msg):
        log.info(output_messages['INFO_COMMIT_REPO'] % (self.__path, file), class_name=METADATA_MANAGER_CLASS_NAME)
        repo = Repo(self.__path)
        repo.index.add([file])
        return repo.index.commit(msg)

    def tag_add(self, tag):
        repo = Repo(self.__path)
        return repo.create_tag(tag, message='Automatic tag "{0}"'.format(tag))

    @Halo(text='Pushing metadata to the git repository', spinner='dots')
    def push(self):
        log.debug(output_messages['DEBUG_PUSH'] % self.__path, class_name=METADATA_MANAGER_CLASS_NAME)
        repo = Repo(self.__path)
        try:
            self.validate_blank_remote_url()
            for i in repo.remotes.origin.push(tags=True):
                if (i.flags & PushInfo.ERROR) == PushInfo.ERROR:
                    raise RuntimeError(output_messages['ERROR_PUSH_METADATA'])

            for i in repo.remotes.origin.push():
                if (i.flags & PushInfo.ERROR) == PushInfo.ERROR:
                    raise RuntimeError(output_messages['ERROR_PUSH_METADATA'])
        except GitError as e:
            err = e.stderr
            match = re.search("stderr: 'fatal:((?:.|\\s)*)'", err)
            if match:
                err = match.group(1)
                raise GitError(err)

    def fetch(self):
        try:
            log.debug(output_messages['DEBUG_FETCH'] % self.__path, class_name=METADATA_MANAGER_CLASS_NAME)
            repo = Repo(self.__path)
            self.validate_blank_remote_url()
            repo.remotes.origin.fetch()
        except GitError as e:
            err = e.stderr
            match = re.search('stderr: \'fatal:(.*)\'', err)
            if match:
                err = match.group(1)
                log.error(err, class_name=METADATA_MANAGER_CLASS_NAME)
            else:
                log.error(err, class_name=METADATA_MANAGER_CLASS_NAME)
            return False

    def list_tags(self, spec, full_info=False):
        tags = []
        try:
            repo = Repo(self.__path)
            r_tags = repo.tags if full_info else repo.git.tag(sort='creatordate').split('\n')
            for tag in r_tags:
                if f'__{spec}__' in str(tag):
                    tags.append(tag)

        except Exception:
            log.error(output_messages['ERROR_INVALID_REPOSITORY'], class_name=METADATA_MANAGER_CLASS_NAME)
        return tags

    def delete_tag(self, tag):
        """
        Method to delete a specific existent tag.
        Not implemented yet.
        """
        pass

    def _usrtag_exists(self, usrtag):
        repo = Repo(self.__path)
        sutag = usrtag._get()
        for tag in repo.tags:
            stag = str(tag)
            if sutag in stag:
                return True
        return False

    def _tag_exists(self, tag):
        tags = []
        repo = Repo(self.__path)
        if tag in repo.tags:
            tags.append(tag)
        model_tag = '__'.join(tag.split('__')[-3:])
        for r_tag in repo.tags:
            if model_tag == str(r_tag):
                tags.append(str(r_tag))
        return tags

    def __realname(self, path, root=None):
        if root is not None:
            path = os.path.join(root, path)
        result = os.path.basename(path)
        return result

    @staticmethod
    def get_metadata_path_and_prefix(metadata_path):
        prefix = 0
        if metadata_path != '/':
            if metadata_path.endswith('/'):
                metadata_path = metadata_path[:-1]
            prefix = len(metadata_path)
        return metadata_path, prefix

    def format_output_path(self, title, prefix, metadata_path):
        output = title + '\n'
        for root, dirs, files in os.walk(metadata_path):
            if root == metadata_path:
                continue
            if '.git' in root:
                continue

            level = root[prefix:].count(os.sep)
            indent = sub_indent = ''
            if level > 0:
                indent = '|   ' * (level - 1) + '|-- '
            sub_indent = '|   ' * (level) + '|-- '
            output += '{}{}\n'.format(indent, self.__realname(root))
            for d in dirs:
                if os.path.islink(os.path.join(root, d)):
                    output += '{}{}\n'.format(sub_indent, self.__realname(d, root=root))
        return output

    def list(self, title='ML Datasets'):
        metadata_path, prefix = self.get_metadata_path_and_prefix(self.__path)
        output = self.format_output_path(title, prefix, metadata_path)

        if output != (title + '\n'):
            print(output)
        else:
            log.error(output_messages['ERROR_NONE_ENTITY_MANAGED'])

    @staticmethod
    def metadata_print(metadata_file, spec_name):
        md = yaml_load(metadata_file)

        sections = EntityType.to_list()
        for section in sections:
            spec_key = get_spec_key(section)
            if section in EntityType.to_list():
                try:
                    md[spec_key]  # 'hack' to ensure we don't print something useless
                    # 'dataset' not present in 'model' and vice versa
                    print('-- %s : %s --' % (section, spec_name))
                except Exception:
                    continue
            elif section not in EntityType.to_list():
                print('-- %s --' % (section))
            try:
                print(get_yaml_str(md[spec_key]))
            except Exception:
                continue

    def sha_from_tag(self, tag):
        try:
            r = Repo(self.__path)
            return r.git.rev_list(tag).split('\n', 1)[0]
        except Exception:
            return None

    def git_user_config(self):
        r = Repo(self.__path)
        reader = r.config_reader()
        config = {}
        types = ['email', 'name']
        for type in types:
            try:
                field = reader.get_value('user', type)
                config[type] = field
            except Exception:
                config[type] = None
        return config

    def metadata_spec_from_name(self, specname):
        specs = []
        for root, dirs, files in os.walk(self.__path):
            if '.git' in root:
                continue
            if specname in root:
                specs.append(os.path.join(root, specname + SPEC_EXTENSION))
        return specs

    def show(self, spec):
        specs = self.metadata_spec_from_name(spec)
        for specpath in specs:
            self.metadata_print(specpath, spec)

    def reset(self):
        repo = Repo(self.__path)
        # get current tag reference
        tag = self.get_current_tag()
        # reset
        try:
            repo.head.reset(HEAD_1, index=True, working_tree=True, paths=None)
        except GitError as g:
            if 'Failed to resolve \'HEAD~1\' as a valid revision.' in g.stderr:
                log.error(output_messages['ERROR_NO_COMMIT_TO_BACK'],
                          class_name=METADATA_MANAGER_CLASS_NAME)
            raise g
        # delete the associated tag
        repo.delete_tag(tag)

    def get_metadata_manifest(self, path):
        if os.path.isfile(path):
            return Manifest(path)
        return None

    @staticmethod
    def remove_deleted_files_meta_manifest(manifest, deleted_files):
        if manifest is not None:
            for file in deleted_files:
                manifest.rm_file(file)
            manifest.save()

    @staticmethod
    def remove_files_added_after_base_tag(manifest, ws_path):
        files_added = []
        if manifest is not None:
            for key, value in manifest.get_yaml().items():
                for key_value in value:
                    if not os.path.exists(os.path.join(ws_path, key_value)):
                        files_added.append(key_value)
            for file in files_added:
                manifest.rm_file(file)
            manifest.save()

    def get_current_tag(self):
        repo = Repo(self.__path)
        tag = next((tag for tag in repo.tags if tag.commit == repo.head.commit), None)
        return tag

    @staticmethod
    def __sort_tag_by_date(elem):
        return elem.commit.authored_date

    def _get_spec_content(self, spec, sha):
        entity_dir = get_entity_dir(self.__repo_type, spec, root_path=self.__path)
        spec_path = '/'.join([posix_path(entity_dir), spec + SPEC_EXTENSION])

        return yaml_load_str(self._get_spec_content_from_ref(sha, spec_path))

    def _get_metrics(self, spec, sha):
        spec_file = self._get_spec_content(spec, sha)

        entity_spec_key = get_spec_key(self.__repo_type)
        metrics = spec_file[entity_spec_key].get(PERFORMANCE_KEY, {})
        metrics_table = PrettyTable()
        if not metrics:
            return ''

        metrics_table.field_names = ['Name', 'Value']
        metrics_table.align['Name'] = 'l'
        metrics_table.align['Value'] = 'l'
        for key, value in metrics.items():
            metrics_table.add_row([key, value])
        return '\n{}:\n{}'.format(PERFORMANCE_KEY, metrics_table.get_string())

    def _get_ordered_entity_tags(self, spec):
        tags = self.list_tags(spec, True)
        if len(tags) == 0:
            raise RuntimeError(output_messages['ERROR_NO_ENTITY_LOG'] % spec)
        tags.sort(key=self.__sort_tag_by_date)
        return tags

    def get_log_info(self, spec, fullstat=False, specialized_data_info=None):
        formatted = ''
        tags = self._get_ordered_entity_tags(spec)

        for tag in tags:
            formatted += '\n' + self.get_formatted_log_info(tag, fullstat)
            formatted += self._get_metrics(spec, tag.commit)
            if specialized_data_info:
                value = next(specialized_data_info, '')
                formatted += value

        return formatted

    @staticmethod
    def _get_related_entity_info(spec_file, entity_type):
        related_entity = spec_file.get(entity_type, None)
        if related_entity:
            entity_tag = related_entity['tag']
            _, entity_name, version = spec_parse(entity_tag)
            return entity_tag, '{} - ({})'.format(entity_name, version)
        return None, None

    @staticmethod
    def _create_tag_info_table(tag_info, metrics):
        tag_table = PrettyTable()
        tag_table.field_names = ['Name', 'Value']
        tag_table.add_row([DATE, tag_info[DATE]])
        tag_table.add_row([RELATED_DATASET_TABLE_INFO, tag_info[RELATED_DATASET_TABLE_INFO]])
        tag_table.add_row([RELATED_LABELS_TABLE_INFO, tag_info[RELATED_LABELS_TABLE_INFO]])
        for key, value in metrics.items():
            tag_table.add_row([key, value])
        return tag_table

    def _get_tag_info(self, spec, tag):
        entity_spec_key = get_spec_key(self.__repo_type)
        spec_file = self._get_spec_content(spec, tag.commit)[entity_spec_key]
        related_dataset_tag, related_dataset_info = self._get_related_entity_info(spec_file, DATASET_SPEC_KEY)
        related_labels_tag, related_labels_info = self._get_related_entity_info(spec_file, LABELS_SPEC_KEY)
        tag_info = {
            DATE: time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(tag.commit.authored_date)),
            TAG: tag.name,
            RELATED_DATASET_TABLE_INFO: related_dataset_info,
            RELATED_LABELS_TABLE_INFO: related_labels_info}
        metrics = spec_file.get(PERFORMANCE_KEY, {})
        tag_info[PERFORMANCE_KEY] = metrics
        tag_table = self._create_tag_info_table(tag_info, metrics)
        return tag_info, tag_table

    def get_metrics_info(self, entity_name, export_path=None):
        tags = self._get_ordered_entity_tags(entity_name)
        tags_info = []
        for tag in tags:
            tag_info, tag_info_table = self._get_tag_info(entity_name, tag)
            tags_info.append(tag_info)
            if not export_path:
                print('{}: {}\n{}\n'.format(TAG, tag.name, tag_info_table.get_string()))
        return tags_info

    @staticmethod
    def _format_data_for_csv(tag_infos):
        csv_header = [DATE, TAG, RELATED_DATASET_TABLE_INFO, RELATED_LABELS_TABLE_INFO]
        for info in tag_infos:
            for metric_key in info[PERFORMANCE_KEY]:
                info[metric_key] = info[PERFORMANCE_KEY][metric_key]
                if metric_key not in csv_header:
                    csv_header.append(metric_key)
        return csv_header, tag_infos

    @staticmethod
    def _export_metrics_to_json(entity_name, file_path, tags_info):
        data = {'model_name': entity_name, 'tags_metrics': tags_info}
        file_path += '.' + FileType.JSON.value
        formatted_data = json.dumps(data)
        with open(file_path, 'w') as outfile:
            outfile.write(formatted_data)
        return json.loads(formatted_data), file_path

    def _export_metrics_to_csv(self, file_path, tags_info):
        csv_header, data_formatted = self._format_data_for_csv(tags_info)
        file_path += '.' + FileType.CSV.value
        create_csv_file(file_path, csv_header, data_formatted)
        with open(file_path) as csv_file:
            return io.StringIO(csv_file.read()), file_path

    def export_metrics(self, entity_name, export_path, export_type, tags_info, log_export_info=True):
        file_name = '{}-{}'.format(entity_name, PERFORMANCE_KEY)
        file_path = os.path.join(export_path, file_name)
        if export_type == FileType.JSON.value:
            data, file_path = self._export_metrics_to_json(entity_name, file_path, tags_info)
        elif export_type == FileType.CSV.value:
            data, file_path = self._export_metrics_to_csv(file_path, tags_info)
        else:
            log.error(output_messages['ERROR_INVALID_TYPE_OF_FILE'] % (FileType.to_list()))
            return
        if log_export_info:
            log.info(output_messages['INFO_METRICS_EXPORTED'].format(file_path))
        return data

    @staticmethod
    def _get_spec_content_from_ref(ref, spec_path):
        entity_spec = ref.tree / spec_path
        return io.BytesIO(entity_spec.data_stream.read())

    def get_specs_to_compare(self, spec):
        entity = self.__repo_type
        spec_manifest_key = 'manifest'
        tags = self.list_tags(spec, True)

        entity_dir = get_entity_dir(entity, spec, root_path=self.__path)
        spec_path = '/'.join([posix_path(entity_dir), spec + SPEC_EXTENSION])
        for tag in tags:
            current_ref = tag.commit
            parents = current_ref.parents
            base_spec = {entity: {spec_manifest_key: {}}}

            if parents:
                base_ref = parents[0]
                base_spec = yaml_load_str(self._get_spec_content_from_ref(base_ref, spec_path))

            current_spec = yaml_load_str(self._get_spec_content_from_ref(current_ref, spec_path))
            yield current_spec[entity][spec_manifest_key], base_spec[entity][spec_manifest_key]

    def get_formatted_log_info(self, tag, fullstat):
        commit = tag.commit
        info_format = '\n{}: {}'
        info = ''
        info += info_format.format(TAG, str(tag))
        info += info_format.format(AUTHOR, commit.author.name)
        info += info_format.format(EMAIL, commit.author.email)
        info += info_format.format(DATE, time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(commit.authored_date)))
        info += info_format.format(MESSAGE, commit.message)

        if fullstat:
            added, deleted, size, amount = self.get_ref_diff(tag)
            if len(added) > 0:
                added_list = list(added)
                info += '\n\n{} [{}]:\n\t{}'.format(ADDED, len(added_list), '\n\t'.join(added_list))
            if len(deleted) > 0:
                deleted_list = list(deleted)
                info += '\n\n{} [{}]:\n\t{}'.format(DELETED, len(deleted_list), '\n\t'.join(deleted_list))
            if len(size) > 0:
                info += '\n\n{}: {}'.format(SIZE, '\n\t'.join(size))
            if len(amount) > 0:
                info += '\n\n{}: {}'.format(AMOUNT, '\n\t'.join(amount))

        return info

    def get_ref_diff(self, tag):
        repo = Repo(self.__path)
        commit = tag.commit
        parents = tag.commit.parents
        added_files = []
        deleted_files = []
        size_files = []
        amount_files = []
        if len(parents) > 0:
            diff = repo.git.diff(str(parents[0]), str(commit))
            added_files = re.findall(RGX_ADDED_FILES, diff)
            deleted_files = re.findall(RGX_DELETED_FILES, diff)
            size_files = re.findall(RGX_SIZE_FILES, diff)
            amount_files = re.findall(RGX_AMOUNT_FILES, diff)

        return added_files, deleted_files, size_files, amount_files

    def validate_blank_remote_url(self):
        blank_url = ''
        repo = Repo(self.__path)
        for url in repo.remote().urls:
            if url == blank_url:
                git_error = GitError()
                git_error.stderr = output_messages['ERROR_REMOTE_NOT_FOUND']
                raise git_error

    def delete_git_reference(self):
        try:
            self.remote_set_url('')
        except GitError as e:
            log.error(e.stderr, class_name=METADATA_MANAGER_CLASS_NAME)
            return False
        return True

    def move_metadata_dir(self, old_directory, new_directory):
        repo = Repo(self.__path)
        old_path = os.path.join(self.__path, old_directory)
        new_path = os.path.join(self.__path, os.path.dirname(new_directory))
        ensure_path_exists(new_path)
        repo.git.mv([old_path, new_path])
        if not os.listdir(os.path.dirname(old_path)):
            clear(os.path.dirname(old_path))


class MetadataManager(MetadataRepo):
    def __init__(self, config, repo_type=EntityType.MODELS.value):
        self.path = get_metadata_path(config, repo_type)
        self.git = config[repo_type]['git']

        super(MetadataManager, self).__init__(self.git, self.path, repo_type)


class MetadataObject(object):
    def __init__(self):
        pass
