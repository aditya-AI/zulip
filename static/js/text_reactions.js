var text_reactions = (function () {
var exports = {};

function send_reaction_ajax(message_id, text, operation) {
    var args = {
        url: '/json/messages/' + message_id + '/text_reactions/' + encodeURIComponent(text),
        data: {},
        success: function () {},
        error: function (xhr) {
            var response = channel.xhr_error_message("Error sending reaction", xhr);
            blueslip.warn(response);
        },
    };
    if (operation === 'add') {
        channel.put(args);
    } else if (operation === 'remove') {
        channel.del(args);
    }
}

exports.toggle_reaction = function (message_id, text) {
    // This toggles the current user's text reaction

    var message = get_message(message_id);
    if (!message) {
        return;
    }

    /*var has_reacted = exports.current_user_has_reacted_to_emoji(message, emoji_name);
    var operation = has_reacted ? 'remove' : 'add';*/
    var operation = 'add';
    send_reaction_ajax(message_id, emoji_name, operation);

    // The next line isn't always necessary, but it is harmless/quick
    // when no popovers are there.*/
    emoji_picker.hide_emoji_popover();
};
}());

if (typeof module !== 'undefined') {
    module.exports = text_reactions;
}
