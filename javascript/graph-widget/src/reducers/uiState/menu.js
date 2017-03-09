import { Map } from 'immutable'

const SET_ACTIVE_MENU_ITEM = 'graph-widget/uiState/menu/SET_ACTIVE_MENU_ITEM';


const initialState = Map({
  activeItem: 'bio'
});
export default function reducer(state = initialState, action) {
  switch (action.type) {
    case SET_ACTIVE_MENU_ITEM:
      return state.merge({
        activeItem: action.payload
      });
    default:
      return state
  }
}

export function setActiveMenuItem(payload) {
  return {
    type: SET_ACTIVE_MENU_ITEM,
    payload
  }
}
