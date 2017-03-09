import React, { Component } from 'react'
import { connect } from 'react-redux'
import { bindActionCreators } from 'redux'

import { fetchNodeList } from '../reducers/uiState/accessRuleControls'

class AccessRules extends Component {

  displayName = 'Access Rules';

  constructor(props) {
    super(props)
  }

  componentDidMount() {
    this.props.actions.fetchNodeList()
  }

  render() {
    return (
      <p>
        Access rules
      </p>
    )
  }
}

export default connect(
  state => ({
    uiState: state.uiState
  }),
  dispatch => ({
    actions: bindActionCreators(Object.assign({}, { fetchNodeList }), dispatch)
  })
)(AccessRules)