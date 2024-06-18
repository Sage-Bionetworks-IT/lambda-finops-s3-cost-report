import logging
import os

import synapseclient as syn

LOG = logging.getLogger(__name__)
LOG.setLevel(logging.DEBUG)

# Create a Synapse client
# The lambda homedir is not writeable, put the cache in /tmp
syn_client = syn.Synapse(cache_root_dir='/tmp/synapse')


def get_team_sage_members():
    """
    Get a list of Team Sage emails from Synapse
    """

    synapse_id = os.environ['SYNAPSE_TEAM_ID']
    synapse_domain = os.environ['SYNAPSE_TEAM_DOMAIN']

    team_sage = []

    syn_team = syn_client.getTeam(synapse_id)
    syn_members = syn_client.getTeamMembers(syn_team)
    for m in syn_members:
        email = m['member']['userName'] + synapse_domain
        team_sage.append(email)

    LOG.info(f"Members of Team Sage: {team_sage}")

    return team_sage
