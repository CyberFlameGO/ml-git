"""
© Copyright 2020 HP Development Company, L.P.
SPDX-License-Identifier: GPL-2.0-only
"""
import os
import pathlib
import unittest

import pytest

from ml_git.ml_git_message import output_messages
from tests.integration.commands import MLGIT_INIT, MLGIT_REMOTE_ADD, MLGIT_ENTITY_INIT, MLGIT_COMMIT, MLGIT_PUSH, \
    MLGIT_CHECKOUT, MLGIT_CREATE, MLGIT_ADD
from tests.integration.helper import ERROR_MESSAGE, create_spec, add_file, ML_GIT_DIR, clear, SFTP_BUCKET_PATH, \
    FAKE_SSH_KEY_PATH, FAKE_SSH_KEY_PATH_WITH_PASS
from tests.integration.helper import check_output, GIT_PATH
from tests.integration.output_messages import messages


@pytest.mark.usefixtures('tmp_dir', 'start_local_git_server', 'switch_to_tmp_dir')
class SFTPAcceptanceTests(unittest.TestCase):
    repo_type = 'dataset'
    store_type = 'sftph'
    bucket = 'mlgit'
    dataset_name = 'dataset-ex'
    workspace = os.path.join(repo_type, dataset_name)

    def set_up_push(self, create_know_file=False):
        os.makedirs(self.workspace)
        create_spec(self, self.repo_type, self.tmp_dir, version=1, mutability='strict', store_type=self.store_type)

        self.assertIn(messages[0], check_output(MLGIT_INIT))
        self.assertIn(messages[2] % (GIT_PATH, self.repo_type),
                      check_output(MLGIT_REMOTE_ADD % (self.repo_type, GIT_PATH)))
        self.assertIn(messages[87] % (self.store_type, self.bucket),
                      check_output('ml-git repository store add %s --type=%s' %
                                   ('mlgit --username=mlgit_user '
                                    '--endpoint-url=127.0.0.1 --port=9922 --private-key=' + FAKE_SSH_KEY_PATH, self.store_type)))
        self.assertNotIn(ERROR_MESSAGE, check_output(MLGIT_ENTITY_INIT % 'dataset'))

        if create_know_file:
            with open(os.path.join(self.repo_type, self.repo_type+'-ex', 'file'), 'wt') as z:
                z.write(str('0' * 10011))
        add_file(self, self.repo_type, '', 'new')

        metadata_path = os.path.join(ML_GIT_DIR, self.repo_type, 'metadata')
        self.assertIn(messages[17] % (os.path.join(self.tmp_dir, metadata_path),
                                      os.path.join('computer-vision', 'images', self.dataset_name)),
                      check_output(MLGIT_COMMIT % (self.repo_type, self.dataset_name, '')))
        HEAD = os.path.join(ML_GIT_DIR, self.repo_type, 'refs', self.dataset_name, 'HEAD')
        self.assertTrue(os.path.exists(HEAD))

    def set_up_push_with_pass(self, create_know_file=False):
        os.makedirs(self.workspace)
        create_spec(self, self.repo_type, self.tmp_dir, version=1, mutability='strict', store_type=self.store_type)

        self.assertIn(messages[0], check_output(MLGIT_INIT))
        self.assertIn(messages[2] % (GIT_PATH, self.repo_type),
                      check_output(MLGIT_REMOTE_ADD % (self.repo_type, GIT_PATH)))
        self.assertIn(messages[87] % (self.store_type, self.bucket),
                      check_output('ml-git repository store add %s --type=%s' %
                                   ('mlgit --username=mlgit_user '
                                    '--endpoint-url=127.0.0.1 --port=9922 --private-key=' + FAKE_SSH_KEY_PATH_WITH_PASS, self.store_type)))
        self.assertNotIn(ERROR_MESSAGE, check_output(MLGIT_ENTITY_INIT % 'dataset'))

        if create_know_file:
            with open(os.path.join(self.repo_type, self.repo_type+'-ex', 'file'), 'wt') as z:
                z.write(str('0' * 10011))
        add_file(self, self.repo_type, '', 'new')

        metadata_path = os.path.join(ML_GIT_DIR, self.repo_type, 'metadata')
        self.assertIn(messages[17] % (os.path.join(self.tmp_dir, metadata_path),
                                      os.path.join('computer-vision', 'images', self.dataset_name)),
                      check_output(MLGIT_COMMIT % (self.repo_type, self.dataset_name, '')))
        HEAD = os.path.join(ML_GIT_DIR, self.repo_type, 'refs', self.dataset_name, 'HEAD')
        self.assertTrue(os.path.exists(HEAD))

    def check_amount_of_files(self, expected_files):
        file_count = 0
        for path in pathlib.Path(SFTP_BUCKET_PATH).iterdir():
            if path.is_file():
                file_count += 1
        self.assertEqual(file_count, expected_files)
 
    # @pytest.mark.usefixtures('start_local_git_server', 'switch_to_tmp_dir')
    # def test_01_create_sftp_storage(self):
    #     self.assertIn(messages[0], check_output(MLGIT_INIT))
    #     self.assertIn(messages[2] % (GIT_PATH, self.repo_type), check_output(MLGIT_REMOTE_ADD % (self.repo_type, GIT_PATH)))
    #     self.assertIn(messages[87] % (self.store_type, self.bucket),
    #                   check_output('ml-git repository store add %s --type=%s' %
    #                                ('mlgit --username=mlgit_user '
    #                                 '--endpoint-url=127.0.0.1 --port=9922 --private-key=' + FAKE_SSH_KEY_PATH, self.store_type)))
    #     self.assertNotIn(ERROR_MESSAGE, check_output(MLGIT_ENTITY_INIT % self.repo_type))

    # @pytest.mark.usefixtures('start_local_git_server', 'switch_to_tmp_dir')
    # def test_02_push_file(self):
    #     self.set_up_push()
    #     number_of_files_in_bucket = 0
    #     self.check_amount_of_files(number_of_files_in_bucket)
    #     self.assertNotIn(ERROR_MESSAGE, check_output(MLGIT_PUSH % (self.repo_type, self.dataset_name)))
    #     number_of_files_in_bucket = 10
    #     self.check_amount_of_files(number_of_files_in_bucket)

    # @pytest.mark.usefixtures('start_local_git_server', 'switch_to_tmp_dir')
    # def test_03_checkout(self):
    #     self.set_up_push()
    #     self.assertNotIn(ERROR_MESSAGE, check_output(MLGIT_PUSH % (self.repo_type, self.dataset_name)))
    #     clear(self.workspace)
    #     clear(os.path.join(ML_GIT_DIR, self.repo_type))

    #     self.assertNotIn(ERROR_MESSAGE, check_output(MLGIT_ENTITY_INIT % self.repo_type))
    #     self.assertNotIn(ERROR_MESSAGE, check_output(MLGIT_CHECKOUT % (self.repo_type, self.dataset_name)))
    #     ws_path = os.path.join(self.tmp_dir, self.repo_type, 'computer-vision', 'images', self.dataset_name)
    #     self.assertTrue(os.path.exists(ws_path))
    #     self.assertTrue(os.path.isfile(os.path.join(ws_path, 'newfile0')))
    #     self.assertTrue(os.path.isfile(os.path.join(ws_path, 'newfile1')))

    # @pytest.mark.usefixtures('start_local_git_server', 'switch_to_tmp_dir')
    # def test_04_push_with_wrong_bucket(self):
    #     clear(SFTP_BUCKET_PATH)
    #     os.mkdir(SFTP_BUCKET_PATH)
    #     wrong_bucket = 'wrong_bucket'
    #     self.assertIn(messages[0], check_output(MLGIT_INIT))
    #     self.assertIn(messages[2] % (GIT_PATH, self.repo_type),
    #                   check_output(MLGIT_REMOTE_ADD % (self.repo_type, GIT_PATH)))
    #     self.assertIn(messages[87] % (self.store_type, wrong_bucket),
    #                   check_output('ml-git repository storage add %s --type=%s' %
    #                                (wrong_bucket, self.store_type + ' --username=mlgit_user '
    #                                                                 '--port=9922 --endpoint-url=127.0.0.1 --private-key=' + FAKE_SSH_KEY_PATH)))
    #     self.assertNotIn(ERROR_MESSAGE, check_output(MLGIT_ENTITY_INIT % self.repo_type))

    #     self.assertNotIn(ERROR_MESSAGE, check_output(
    #         MLGIT_CREATE % ('dataset', 'dataset-ex --storage-type=sftph --mutability=strict --category=test --bucket-name=wrong_bucket')))
    #     add_file(self, self.repo_type, '', 'new')

    #     self.assertNotIn(ERROR_MESSAGE, check_output(MLGIT_ADD % (self.repo_type, self.dataset_name, '')))
    #     self.assertNotIn(ERROR_MESSAGE, check_output(MLGIT_COMMIT % (self.repo_type, self.dataset_name, '')))
    #     number_of_files_in_bucket = 0
    #     self.check_amount_of_files(number_of_files_in_bucket)
    #     self.assertIn(output_messages['ERROR_BUCKET_DOES_NOT_EXIST'] % wrong_bucket, check_output(MLGIT_PUSH % (self.repo_type, self.dataset_name)))
    #     self.check_amount_of_files(number_of_files_in_bucket)

    # @pytest.mark.usefixtures('start_local_git_server', 'switch_to_tmp_dir')
    # def test_05_push_with_fail(self):
    #     clear(SFTP_BUCKET_PATH)
    #     os.mkdir(SFTP_BUCKET_PATH)
    #     self.set_up_push(create_know_file=True)

    #     object_path = os.path.join(self.tmp_dir, '.ml-git', self.repo_type, 'objects',
    #                                'hashfs', 'i9', '96', 'zdj7Wi996ViPiddvDGvzjBBACZzw6YfPujBCaPHunVoyiTUCj')
    #     clear(object_path)
    #     number_of_files_in_bucket = 0
    #     self.check_amount_of_files(number_of_files_in_bucket)
    #     self.assertIn(ERROR_MESSAGE, check_output(MLGIT_PUSH % (self.repo_type, self.dataset_name + ' --clearonfail')))

    @pytest.mark.usefixtures('start_local_git_server', 'switch_to_tmp_dir')
    def test_06_check_connection_with_key_pass(self):
        self.set_up_push_with_pass()
        self.assertNotIn('OpenSSH private key file checkints do not match', check_output(MLGIT_PUSH % (self.repo_type, self.dataset_name), "key"))
       