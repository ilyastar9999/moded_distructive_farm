import requests

from __init__ import app
from models import FlagStatus, SubmitResult


RESPONSES = {
    FlagStatus.QUEUED: ['timeout', 'game not started', 'try again later', 'game over', 'is not up',
                        'no such flag'],
    FlagStatus.ACCEPTED: ['accepted', 'congrat'],
    FlagStatus.REJECTED: ['bad', 'wrong', 'expired', 'unknown', 'your own',
                          'too old', 'not in database', 'already submitted', 'invalid flag'],
}
# The RuCTF checksystem adds a signature to all correct flags. It returns
# "invalid flag" verdict if the signature is invalid and "no such flag" verdict if
# the signature is correct but the flag was not found in the checksystem database.
#
# The latter situation happens if a checker puts the flag to the service before putting it
# to the checksystem database. We should resent the flag later in this case.


TIMEOUT = 5


def submit_flags(flags, config):
    r = requests.put(config['SYSTEM_URL'],
                     headers={'X-Team-Token': config['SYSTEM_TOKEN']},
                     json=[item.flag for item in flags], timeout=TIMEOUT)

    unknown_responses = set()
    
    # Check if response is empty or not JSON
    try:
        response_data = r.json()
    except requests.exceptions.JSONDecodeError:
        app.logger.error('Failed to parse JSON response. Status: %s, Body: %s', r.status_code, r.text)
        # Mark all flags as queued to retry later
        for item in flags:
            yield SubmitResult(item.flag, FlagStatus.QUEUED, 'Invalid JSON response from server')
        return
    
    # Parse response JSON
    # Example: [{"flag":"TQB59ZCK4KOHPD8GRPPF9VPYBZ3C28M=","msg":"[TQB59ZCK4KOHPD8GRPPF9VPYBZ3C28M=] Flag is too old"}]
    for item in response_data:
        response = item['msg'].strip()
        response = response.replace('[{}] '.format(item['flag']), '')

        response_lower = response.lower()
        for status, substrings in RESPONSES.items():
            if any(s in response_lower for s in substrings):
                found_status = status
                break
        else:
            found_status = FlagStatus.QUEUED
            if response not in unknown_responses:
                unknown_responses.add(response)
                app.logger.warning('Unknown checksystem response (flag will be resent): %s', response)

        yield SubmitResult(item['flag'], found_status, response)

