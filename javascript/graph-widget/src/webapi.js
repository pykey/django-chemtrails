import 'isomorphic-fetch'

/**
 * Fetch a list of nodes and their relation types
 */
export function fetchNodeList() {
  fetch('//localhost:8000/admin/chemtrails_permissions/accessrule/nodelist/').then((response) => {
    if (response.status >= 400) {
      throw new Error('Bad response from the server')
    }
    return response.json();
  })
}