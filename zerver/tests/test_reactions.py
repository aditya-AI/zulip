# -*- coding: utf-8 -*-

import ujson
from django.http import HttpResponse
from typing import Any, Dict, List, Mapping, Text
from unittest import mock

from zerver.lib.emoji import emoji_name_to_emoji_code
from zerver.lib.request import JsonableError
from zerver.lib.test_helpers import tornado_redirected_to_list, get_display_recipient, \
    get_test_image_file
from zerver.lib.test_classes import ZulipTestCase
from zerver.models import get_realm, Message, Reaction, RealmEmoji, Recipient, UserMessage

class ReactionEmojiTest(ZulipTestCase):
    def test_missing_emoji(self) -> None:
        """
        Sending reaction without emoji fails
        """
        sender = self.example_email("hamlet")
        result = self.client_put('/api/v1/messages/1/emoji_reactions/',
                                 **self.api_auth(sender))
        self.assertEqual(result.status_code, 400)

    def test_add_invalid_emoji(self) -> None:
        """
        Sending invalid emoji fails
        """
        sender = self.example_email("hamlet")
        result = self.client_put('/api/v1/messages/1/emoji_reactions/foo',
                                 **self.api_auth(sender))
        self.assert_json_error(result, "Emoji 'foo' does not exist")

    def test_add_deactivated_realm_emoji(self) -> None:
        """
        Sending deactivated realm emoji fails.
        """
        emoji = RealmEmoji.objects.get(name="green_tick")
        emoji.deactivated = True
        emoji.save(update_fields=['deactivated'])
        sender = self.example_email("hamlet")
        result = self.client_put('/api/v1/messages/1/emoji_reactions/green_tick',
                                 **self.api_auth(sender))
        self.assert_json_error(result, "Emoji 'green_tick' does not exist")

    def test_valid_emoji(self) -> None:
        """
        Reacting with valid emoji succeeds
        """
        sender = self.example_email("hamlet")
        result = self.client_put('/api/v1/messages/1/emoji_reactions/smile',
                                 **self.api_auth(sender))
        self.assert_json_success(result)
        self.assertEqual(200, result.status_code)

    def test_zulip_emoji(self) -> None:
        """
        Reacting with zulip emoji succeeds
        """
        sender = self.example_email("hamlet")
        result = self.client_put('/api/v1/messages/1/emoji_reactions/zulip',
                                 **self.api_auth(sender))
        self.assert_json_success(result)
        self.assertEqual(200, result.status_code)

    def test_valid_emoji_react_historical(self) -> None:
        """
        Reacting with valid emoji on a historical message succeeds
        """
        stream_name = "Saxony"
        self.subscribe(self.example_user("cordelia"), stream_name)
        message_id = self.send_stream_message(self.example_email("cordelia"), stream_name)

        user_profile = self.example_user('hamlet')
        sender = user_profile.email

        # Verify that hamlet did not receive the message.
        self.assertFalse(UserMessage.objects.filter(user_profile=user_profile,
                                                    message_id=message_id).exists())

        # Have hamlet react to the message
        result = self.client_put('/api/v1/messages/%s/emoji_reactions/smile' % (message_id,),
                                 **self.api_auth(sender))
        self.assert_json_success(result)

        # Fetch the now-created UserMessage object to confirm it exists and is historical
        user_message = UserMessage.objects.get(user_profile=user_profile, message_id=message_id)
        self.assertTrue(user_message.flags.historical)
        self.assertTrue(user_message.flags.read)
        self.assertFalse(user_message.flags.starred)

    def test_valid_realm_emoji(self) -> None:
        """
        Reacting with valid realm emoji succeeds
        """
        sender = self.example_email("hamlet")
        emoji_name = 'green_tick'

        result = self.client_put('/api/v1/messages/1/emoji_reactions/%s' % (emoji_name,),
                                 **self.api_auth(sender))
        self.assert_json_success(result)

    def test_emoji_name_to_emoji_code(self) -> None:
        """
        An emoji name is mapped canonically to emoji code.
        """
        realm = get_realm('zulip')

        # Test active realm emoji.
        emoji_code, reaction_type = emoji_name_to_emoji_code(realm, 'green_tick')
        self.assertEqual(emoji_code, 'green_tick')
        self.assertEqual(reaction_type, 'realm_emoji')

        # Test deactivated realm emoji.
        emoji = RealmEmoji.objects.get(name="green_tick")
        emoji.deactivated = True
        emoji.save(update_fields=['deactivated'])
        with self.assertRaises(JsonableError) as exc:
            emoji_name_to_emoji_code(realm, 'green_tick')
        self.assertEqual(str(exc.exception), "Emoji 'green_tick' does not exist")

        # Test ':zulip:' emoji.
        emoji_code, reaction_type = emoji_name_to_emoji_code(realm, 'zulip')
        self.assertEqual(emoji_code, 'zulip')
        self.assertEqual(reaction_type, 'zulip_extra_emoji')

        # Test unicode emoji.
        emoji_code, reaction_type = emoji_name_to_emoji_code(realm, 'astonished')
        self.assertEqual(emoji_code, '1f632')
        self.assertEqual(reaction_type, 'unicode_emoji')

        # Test override unicode emoji.
        overriding_emoji = RealmEmoji.objects.create(
            name='astonished', realm=realm, file_name='astonished')
        emoji_code, reaction_type = emoji_name_to_emoji_code(realm, 'astonished')
        self.assertEqual(emoji_code, 'astonished')
        self.assertEqual(reaction_type, 'realm_emoji')

        # Test deactivate over-ridding realm emoji.
        overriding_emoji.deactivated = True
        overriding_emoji.save(update_fields=['deactivated'])
        emoji_code, reaction_type = emoji_name_to_emoji_code(realm, 'astonished')
        self.assertEqual(emoji_code, '1f632')
        self.assertEqual(reaction_type, 'unicode_emoji')

        # Test override `:zulip:` emoji.
        overriding_emoji = RealmEmoji.objects.create(
            name='zulip', realm=realm, file_name='zulip')
        emoji_code, reaction_type = emoji_name_to_emoji_code(realm, 'zulip')
        self.assertEqual(emoji_code, 'zulip')
        self.assertEqual(reaction_type, 'realm_emoji')

        # Test non-existent emoji.
        with self.assertRaises(JsonableError) as exc:
            emoji_name_to_emoji_code(realm, 'invalid_emoji')
        self.assertEqual(str(exc.exception), "Emoji 'invalid_emoji' does not exist")

class ReactionMessageIDTest(ZulipTestCase):
    def test_missing_message_id(self) -> None:
        """
        Reacting without a message_id fails
        """
        sender = self.example_email("hamlet")
        result = self.client_put('/api/v1/messages//emoji_reactions/smile',
                                 **self.api_auth(sender))
        self.assertEqual(result.status_code, 404)

    def test_invalid_message_id(self) -> None:
        """
        Reacting to an invalid message id fails
        """
        sender = self.example_email("hamlet")
        result = self.client_put('/api/v1/messages/-1/emoji_reactions/smile',
                                 **self.api_auth(sender))
        self.assertEqual(result.status_code, 404)

    def test_inaccessible_message_id(self) -> None:
        """
        Reacting to a inaccessible (for instance, private) message fails
        """
        pm_sender = self.example_email("hamlet")
        pm_recipient = self.example_email("othello")
        reaction_sender = self.example_email("iago")

        result = self.client_post("/api/v1/messages", {"type": "private",
                                                       "content": "Test message",
                                                       "to": pm_recipient},
                                  **self.api_auth(pm_sender))
        self.assert_json_success(result)
        pm_id = result.json()['id']
        result = self.client_put('/api/v1/messages/%s/emoji_reactions/smile' % (pm_id,),
                                 **self.api_auth(reaction_sender))
        self.assert_json_error(result, "Invalid message(s)")

class ReactionTest(ZulipTestCase):
    def test_add_existing_reaction(self) -> None:
        """
        Creating the same reaction twice fails
        """
        pm_sender = self.example_email("hamlet")
        pm_recipient = self.example_email("othello")
        reaction_sender = pm_recipient

        pm = self.client_post("/api/v1/messages", {"type": "private",
                                                   "content": "Test message",
                                                   "to": pm_recipient},
                              **self.api_auth(pm_sender))
        self.assert_json_success(pm)
        content = ujson.loads(pm.content)

        pm_id = content['id']
        first = self.client_put('/api/v1/messages/%s/emoji_reactions/smile' % (pm_id,),
                                **self.api_auth(reaction_sender))
        self.assert_json_success(first)
        second = self.client_put('/api/v1/messages/%s/emoji_reactions/smile' % (pm_id,),
                                 **self.api_auth(reaction_sender))
        self.assert_json_error(second, "Reaction already exists")

    def test_remove_nonexisting_reaction(self) -> None:
        """
        Removing a reaction twice fails
        """
        pm_sender = self.example_email("hamlet")
        pm_recipient = self.example_email("othello")
        reaction_sender = pm_recipient

        pm = self.client_post("/api/v1/messages", {"type": "private",
                                                   "content": "Test message",
                                                   "to": pm_recipient},
                              **self.api_auth(pm_sender))
        self.assert_json_success(pm)
        content = ujson.loads(pm.content)
        pm_id = content['id']
        add = self.client_put('/api/v1/messages/%s/emoji_reactions/smile' % (pm_id,),
                              **self.api_auth(reaction_sender))
        self.assert_json_success(add)

        first = self.client_delete('/api/v1/messages/%s/emoji_reactions/smile' % (pm_id,),
                                   **self.api_auth(reaction_sender))
        self.assert_json_success(first)

        second = self.client_delete('/api/v1/messages/%s/emoji_reactions/smile' % (pm_id,),
                                    **self.api_auth(reaction_sender))
        self.assert_json_error(second, "Reaction does not exist")

    def test_remove_existing_reaction_with_renamed_emoji(self) -> None:
        """
        Removes an old existing reaction but the name of emoji got changed during
        various emoji infra changes.
        """
        sender = self.example_email("hamlet")
        result = self.client_put('/api/v1/messages/1/emoji_reactions/smile',
                                 **self.api_auth(sender))
        self.assert_json_success(result)

        with mock.patch('zerver.lib.emoji.name_to_codepoint', name_to_codepoint={}):
            result = self.client_delete('/api/v1/messages/1/emoji_reactions/smile',
                                        **self.api_auth(sender))
            self.assert_json_success(result)

    def test_remove_existing_reaction_with_deactivated_realm_emoji(self) -> None:
        """
        Removes an old existing reaction but the realm emoji used there has been deactivated.
        """
        sender = self.example_email("hamlet")
        result = self.client_put('/api/v1/messages/1/emoji_reactions/green_tick',
                                 **self.api_auth(sender))
        self.assert_json_success(result)

        # Deactivate realm emoji.
        emoji = RealmEmoji.objects.get(name="green_tick")
        emoji.deactivated = True
        emoji.save(update_fields=['deactivated'])

        result = self.client_delete('/api/v1/messages/1/emoji_reactions/green_tick',
                                    **self.api_auth(sender))
        self.assert_json_success(result)

class ReactionEventTest(ZulipTestCase):
    def test_add_event(self) -> None:
        """
        Recipients of the message receive the reaction event
        and event contains relevant data
        """
        pm_sender = self.example_user('hamlet')
        pm_recipient = self.example_user('othello')
        reaction_sender = pm_recipient

        result = self.client_post("/api/v1/messages", {"type": "private",
                                                       "content": "Test message",
                                                       "to": pm_recipient.email},
                                  **self.api_auth(pm_sender.email))
        self.assert_json_success(result)
        pm_id = result.json()['id']

        expected_recipient_ids = set([pm_sender.id, pm_recipient.id])

        events = []  # type: List[Mapping[str, Any]]
        with tornado_redirected_to_list(events):
            result = self.client_put('/api/v1/messages/%s/emoji_reactions/smile' % (pm_id,),
                                     **self.api_auth(reaction_sender.email))
        self.assert_json_success(result)
        self.assertEqual(len(events), 1)

        event = events[0]['event']
        event_user_ids = set(events[0]['users'])

        self.assertEqual(expected_recipient_ids, event_user_ids)
        self.assertEqual(event['user']['email'], reaction_sender.email)
        self.assertEqual(event['type'], 'reaction')
        self.assertEqual(event['op'], 'add')
        self.assertEqual(event['emoji_name'], 'smile')
        self.assertEqual(event['message_id'], pm_id)

    def test_remove_event(self) -> None:
        """
        Recipients of the message receive the reaction event
        and event contains relevant data
        """
        pm_sender = self.example_user('hamlet')
        pm_recipient = self.example_user('othello')
        reaction_sender = pm_recipient

        result = self.client_post("/api/v1/messages", {"type": "private",
                                                       "content": "Test message",
                                                       "to": pm_recipient.email},
                                  **self.api_auth(pm_sender.email))
        self.assert_json_success(result)
        content = result.json()
        pm_id = content['id']

        expected_recipient_ids = set([pm_sender.id, pm_recipient.id])

        add = self.client_put('/api/v1/messages/%s/emoji_reactions/smile' % (pm_id,),
                              **self.api_auth(reaction_sender.email))
        self.assert_json_success(add)

        events = []  # type: List[Mapping[str, Any]]
        with tornado_redirected_to_list(events):
            result = self.client_delete('/api/v1/messages/%s/emoji_reactions/smile' % (pm_id,),
                                        **self.api_auth(reaction_sender.email))
        self.assert_json_success(result)
        self.assertEqual(len(events), 1)

        event = events[0]['event']
        event_user_ids = set(events[0]['users'])

        self.assertEqual(expected_recipient_ids, event_user_ids)
        self.assertEqual(event['user']['email'], reaction_sender.email)
        self.assertEqual(event['type'], 'reaction')
        self.assertEqual(event['op'], 'remove')
        self.assertEqual(event['emoji_name'], 'smile')
        self.assertEqual(event['message_id'], pm_id)

class DefaultEmojiReactionTests(ZulipTestCase):
    def post_reaction(self, reaction_info, message_id=1, sender='hamlet'):
        # type: (Dict[str, str], int, str) -> HttpResponse
        reaction_info['reaction_type'] = 'unicode_emoji'
        sender = self.example_email(sender)
        result = self.client_post('/api/v1/messages/%s/reactions' % (message_id,),
                                  reaction_info,
                                  **self.api_auth(sender))
        return result

    def delete_reaction(self, reaction_info, message_id=1, sender='hamlet'):
        # type: (Dict[str, str], int, str) -> HttpResponse
        reaction_info['reaction_type'] = 'unicode_emoji'
        sender = self.example_email(sender)
        result = self.client_delete('/api/v1/messages/%s/reactions' % (message_id,),
                                    reaction_info,
                                    **self.api_auth(sender))
        return result

    def get_message_reactions(self, message_id, emoji_code, reaction_type):
        # type: (int, Text, Text) -> List[Reaction]
        message = Message.objects.get(id=message_id)
        reactions = Reaction.objects.filter(message=message,
                                            emoji_code=emoji_code,
                                            reaction_type=reaction_type)
        return list(reactions)

    def setUp(self):
        # type: () -> None
        reaction_info = {
            'emoji_name': 'hamburger',
            'emoji_code': '1f354',
        }
        result = self.post_reaction(reaction_info)
        self.assert_json_success(result)

    def test_add_default_emoji_reaction(self):
        # type: () -> None
        reaction_info = {
            'emoji_name': 'thumbs_up',
            'emoji_code': '1f44d',
        }
        result = self.post_reaction(reaction_info)
        self.assert_json_success(result)

    def test_add_default_emoji_invalid_code(self):
        # type: () -> None
        reaction_info = {
            'emoji_name': 'hamburger',
            'emoji_code': 'TBD',
        }
        result = self.post_reaction(reaction_info)
        self.assert_json_error(result, 'Emoji for this emoji code not found.')

    def test_add_default_emoji_invalid_name(self):
        # type: () -> None
        reaction_info = {
            'emoji_name': 'non-existent',
            'emoji_code': '1f44d',
        }
        result = self.post_reaction(reaction_info)
        self.assert_json_error(result, 'Invalid emoji name.')

    def test_add_to_existing_renamed_default_emoji_reaction(self):
        # type: () -> None
        hamlet = self.example_user('hamlet')
        message = Message.objects.get(id=1)
        reaction = Reaction.objects.create(user_profile=hamlet,
                                           message=message,
                                           emoji_name='old_name',
                                           emoji_code='1f603',
                                           reaction_type='unicode_emoji',
                                           )
        reaction_info = {
            'emoji_name': 'smiley',
            'emoji_code': '1f603',
        }
        result = self.post_reaction(reaction_info, sender='AARON')
        self.assert_json_success(result)

        reactions = self.get_message_reactions(1, '1f603', 'unicode_emoji')
        for reaction in reactions:
            self.assertEqual(reaction.emoji_name, 'old_name')

    def test_add_duplicate_reaction(self):
        # type: () -> None
        reaction_info = {
            'emoji_name': 'non-existent',
            'emoji_code': '1f354',
        }
        result = self.post_reaction(reaction_info)
        self.assert_json_error(result, 'Reaction already exists.')

    def test_preserve_non_canonical_name(self):
        # type: () -> None
        reaction_info = {
            'emoji_name': '+1',
            'emoji_code': '1f44d',
        }
        result = self.post_reaction(reaction_info)
        self.assert_json_success(result)

        reactions = self.get_message_reactions(1, '1f44d', 'unicode_emoji')
        for reaction in reactions:
            self.assertEqual(reaction.emoji_name, '+1')

    def test_reaction_name_collapse(self):
        # type: () -> None
        reaction_info = {
            'emoji_name': '+1',
            'emoji_code': '1f44d',
        }
        result = self.post_reaction(reaction_info)
        self.assert_json_success(result)

        reaction_info['emoji_name'] = 'thumbs_up'
        result = self.post_reaction(reaction_info, sender='AARON')
        self.assert_json_success(result)

        reactions = self.get_message_reactions(1, '1f44d', 'unicode_emoji')
        for reaction in reactions:
            self.assertEqual(reaction.emoji_name, '+1')

    def test_delete_default_emoji_reaction(self):
        # type: () -> None
        reaction_info = {
            'emoji_name': 'hamburger',
            'emoji_code': '1f354',
        }
        result = self.delete_reaction(reaction_info)
        self.assert_json_success(result)

    def test_delete_non_existing_emoji_reaction(self):
        # type: () -> None
        reaction_info = {
            'emoji_name': 'thumbs_up',
            'emoji_code': '1f44d',
        }
        result = self.delete_reaction(reaction_info)
        self.assert_json_error(result, "Reaction doesn't exist.")

    def test_delete_renamed_default_emoji(self):
        # type: () -> None
        hamlet = self.example_user('hamlet')
        message = Message.objects.get(id=1)
        Reaction.objects.create(user_profile=hamlet,
                                message=message,
                                emoji_name='old_name',
                                emoji_code='1f44f',
                                reaction_type='unicode_emoji',
                                )

        reaction_info = {
            'emoji_name': 'new_name',
            'emoji_code': '1f44f',
        }
        result = self.delete_reaction(reaction_info)
        self.assert_json_success(result)

    def test_react_historical(self):
        # type: () -> None
        """
        Reacting with valid emoji on a historical message succeeds.
        """
        stream_name = "Saxony"
        self.subscribe(self.example_user("cordelia"), stream_name)
        message_id = self.send_stream_message(self.example_email("cordelia"), stream_name)

        user_profile = self.example_user('hamlet')

        # Verify that hamlet did not receive the message.
        self.assertFalse(UserMessage.objects.filter(user_profile=user_profile,
                                                    message_id=message_id).exists())

        # Have hamlet react to the message
        reaction_info = {
            'emoji_name': 'hamburger',
            'emoji_code': '1f354',
        }
        result = self.post_reaction(reaction_info, message_id=message_id)
        self.assert_json_success(result)

        # Fetch the now-created UserMessage object to confirm it exists and is historical
        user_message = UserMessage.objects.get(user_profile=user_profile, message_id=message_id)
        self.assertTrue(user_message.flags.historical)
        self.assertTrue(user_message.flags.read)
        self.assertFalse(user_message.flags.starred)

class ZulipExtraEmojiReactionTest(ZulipTestCase):
    def post_zulip_reaction(self, message_id=1, sender='hamlet'):
        # type: (int, Text) -> HttpResponse
        sender = self.example_email(sender)
        reaction_info = {
            'emoji_name': 'zulip',
            'emoji_code': 'zulip',
            'reaction_type': 'zulip_extra_emoji',
        }
        result = self.client_post('/api/v1/messages/%s/reactions' % (message_id,),
                                  reaction_info,
                                  **self.api_auth(sender))
        return result

    def test_add_zulip_emoji_reaction(self):
        # type: () -> None
        result = self.post_zulip_reaction()
        self.assert_json_success(result)

    def test_add_duplicate_zulip_reaction(self):
        # type: () -> None
        result = self.post_zulip_reaction()
        self.assert_json_success(result)

        result = self.post_zulip_reaction()
        self.assert_json_error(result, 'Reaction already exists.')

    def test_delete_zulip_emoji(self):
        # type: () -> None
        result = self.post_zulip_reaction()
        self.assert_json_success(result)

        sender = self.example_email('hamlet')
        reaction_info = {
            'emoji_name': 'zulip',
            'emoji_code': 'zulip',
            'reaction_type': 'zulip_extra_emoji',
        }
        result = self.client_delete('/api/v1/messages/1/reactions',
                                    reaction_info,
                                    **self.api_auth(sender))
        self.assert_json_success(result)

    def test_delete_non_existent_zulip_reaction(self):
        # type: () -> None
        sender = self.example_email('hamlet')
        reaction_info = {
            'emoji_name': 'zulip',
            'emoji_code': 'zulip',
            'reaction_type': 'zulip_extra_emoji',
        }
        result = self.client_delete('/api/v1/messages/1/reactions',
                                    reaction_info,
                                    **self.api_auth(sender))
        self.assert_json_error(result, "Reaction doesn't exist.")

class RealmEmojiReactionTests(ZulipTestCase):
    def post_reaction(self, reaction_info, message_id=1, sender='hamlet'):
        # type: (Dict[str, str], int, str) -> HttpResponse
        reaction_info['reaction_type'] = 'realm_emoji'
        sender = self.example_email(sender)
        result = self.client_post('/api/v1/messages/%s/reactions' % (message_id,),
                                  reaction_info,
                                  **self.api_auth(sender))
        return result

    def delete_reaction(self, reaction_info, message_id=1, sender='hamlet'):
        # type: (Dict[str, str], int, str) -> HttpResponse
        reaction_info['reaction_type'] = 'realm_emoji'
        sender = self.example_email(sender)
        result = self.client_delete('/api/v1/messages/%s/reactions' % (message_id,),
                                    reaction_info,
                                    **self.api_auth(sender))
        return result

    def get_message_reactions(self, message_id, emoji_code, reaction_type):
        # type: (int, Text, Text) -> List[Reaction]
        message = Message.objects.get(id=message_id)
        reactions = Reaction.objects.filter(message=message,
                                            emoji_code=emoji_code,
                                            reaction_type=reaction_type)
        return list(reactions)

    def test_add_realm_emoji(self):
        # type: () -> None
        reaction_info = {
            'emoji_name': 'green_tick',
            'emoji_code': 'green_tick',
        }
        result = self.post_reaction(reaction_info)
        self.assert_json_success(result)

    def test_add_realm_emoji_invalid_code(self):
        # type: () -> None
        reaction_info = {
            'emoji_name': 'green_tick',
            'emoji_code': 'non_existent',
        }
        result = self.post_reaction(reaction_info)
        self.assert_json_error(result, 'Emoji for this emoji code not found.')

    def test_add_deactivated_realm_emoji(self):
        # type: () -> None
        emoji = RealmEmoji.objects.get(name="green_tick")
        emoji.deactivated = True
        emoji.save(update_fields=['deactivated'])

        reaction_info = {
            'emoji_name': 'green_tick',
            'emoji_code': 'green_tick',
        }
        result = self.post_reaction(reaction_info)
        self.assert_json_error(result, 'Emoji for this emoji code not found.')

    def test_add_to_existing_deactivated_realm_emoji_reaction(self):
        # type: () -> None
        reaction_info = {
            'emoji_name': 'green_tick',
            'emoji_code': 'green_tick',
        }
        result = self.post_reaction(reaction_info)
        self.assert_json_success(result)

        emoji = RealmEmoji.objects.get(name="green_tick")
        emoji.deactivated = True
        emoji.save(update_fields=['deactivated'])

        result = self.post_reaction(reaction_info, sender='AARON')
        self.assert_json_success(result)

        reactions = self.get_message_reactions(1, 'green_tick', 'realm_emoji')
        self.assertEqual(len(reactions), 2)

    def test_remove_realm_emoji_reaction(self):
        # type: () -> None
        reaction_info = {
            'emoji_name': 'green_tick',
            'emoji_code': 'green_tick',
        }
        result = self.post_reaction(reaction_info)
        self.assert_json_success(result)

        result = self.delete_reaction(reaction_info)
        self.assert_json_success(result)

    def test_remove_deactivated_realm_emoji_reaction(self):
        # type: () -> None
        reaction_info = {
            'emoji_name': 'green_tick',
            'emoji_code': 'green_tick',
        }
        result = self.post_reaction(reaction_info)
        self.assert_json_success(result)

        emoji = RealmEmoji.objects.get(name="green_tick")
        emoji.deactivated = True
        emoji.save(update_fields=['deactivated'])

        result = self.delete_reaction(reaction_info)
        self.assert_json_success(result)

    def test_remove_non_existent_realm_emoji_reaction(self):
        # type: () -> None
        reaction_info = {
            'emoji_name': 'non_existent',
            'emoji_code': 'TBD',
        }
        result = self.delete_reaction(reaction_info)
        self.assert_json_error(result, "Reaction doesn't exist.")

    def test_invalid_reaction_type(self) -> None:
        reaction_info = {
            'emoji_name': 'zulip',
            'emoji_code': 'zulip',
            'reaction_type': 'nonexistent_emoji_type',
        }
        sender = self.example_email("hamlet")
        message_id = 1
        result = self.client_post('/api/v1/messages/%s/reactions' % (message_id,),
                                  reaction_info,
                                  **self.api_auth(sender))
        self.assert_json_error(result, "Emoji for this emoji code not found.")

class ReactionAPIEventTest(ZulipTestCase):
    def test_add_event(self):
        # type: () -> None
        """
        Recipients of the message receive the reaction event
        and event contains relevant data
        """
        pm_sender = self.example_user('hamlet')
        pm_recipient = self.example_user('othello')
        reaction_sender = pm_recipient

        result = self.client_post("/api/v1/messages", {"type": "private",
                                                       "content": "Test message",
                                                       "to": pm_recipient.email},
                                  **self.api_auth(pm_sender.email))
        self.assert_json_success(result)
        pm_id = result.json()['id']

        expected_recipient_ids = set([pm_sender.id, pm_recipient.id])

        reaction_info = {
            'emoji_name': 'hamburger',
            'emoji_code': '1f354',
            'reaction_type': 'unicode_emoji',
        }
        events = []  # type: List[Mapping[str, Any]]
        with tornado_redirected_to_list(events):
            result = self.client_post('/api/v1/messages/%s/reactions' % (pm_id,),
                                      reaction_info,
                                      **self.api_auth(reaction_sender.email))
        self.assert_json_success(result)
        self.assertEqual(len(events), 1)

        event = events[0]['event']
        event_user_ids = set(events[0]['users'])

        self.assertEqual(expected_recipient_ids, event_user_ids)
        self.assertEqual(event['user']['user_id'], reaction_sender.id)
        self.assertEqual(event['user']['email'], reaction_sender.email)
        self.assertEqual(event['user']['full_name'], reaction_sender.full_name)
        self.assertEqual(event['type'], 'reaction')
        self.assertEqual(event['op'], 'add')
        self.assertEqual(event['message_id'], pm_id)
        self.assertEqual(event['emoji_name'], reaction_info['emoji_name'])
        self.assertEqual(event['emoji_code'], reaction_info['emoji_code'])
        self.assertEqual(event['reaction_type'], reaction_info['reaction_type'])

    def test_remove_event(self):
        # type: () -> None
        """
        Recipients of the message receive the reaction event
        and event contains relevant data
        """
        pm_sender = self.example_user('hamlet')
        pm_recipient = self.example_user('othello')
        reaction_sender = pm_recipient

        result = self.client_post("/api/v1/messages", {"type": "private",
                                                       "content": "Test message",
                                                       "to": pm_recipient.email},
                                  **self.api_auth(pm_sender.email))
        self.assert_json_success(result)
        content = result.json()
        pm_id = content['id']

        expected_recipient_ids = set([pm_sender.id, pm_recipient.id])

        reaction_info = {
            'emoji_name': 'hamburger',
            'emoji_code': '1f354',
            'reaction_type': 'unicode_emoji',
        }
        add = self.client_post('/api/v1/messages/%s/reactions' % (pm_id,),
                               reaction_info,
                               **self.api_auth(reaction_sender.email))
        self.assert_json_success(add)

        events = []  # type: List[Mapping[str, Any]]
        with tornado_redirected_to_list(events):
            result = self.client_delete('/api/v1/messages/%s/reactions' % (pm_id,),
                                        reaction_info,
                                        **self.api_auth(reaction_sender.email))
        self.assert_json_success(result)
        self.assertEqual(len(events), 1)

        event = events[0]['event']
        event_user_ids = set(events[0]['users'])

        self.assertEqual(expected_recipient_ids, event_user_ids)
        self.assertEqual(event['user']['user_id'], reaction_sender.id)
        self.assertEqual(event['user']['email'], reaction_sender.email)
        self.assertEqual(event['user']['full_name'], reaction_sender.full_name)
        self.assertEqual(event['type'], 'reaction')
        self.assertEqual(event['op'], 'remove')
        self.assertEqual(event['message_id'], pm_id)
        self.assertEqual(event['emoji_name'], reaction_info['emoji_name'])
        self.assertEqual(event['emoji_code'], reaction_info['emoji_code'])
        self.assertEqual(event['reaction_type'], reaction_info['reaction_type'])
