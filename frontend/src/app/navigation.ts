export type ActiveTab = 'requests' | 'chat';
export type ChatGroupBy = 'system_prompt' | 'system_prompt_first_user' | 'client' | 'model';

export interface NavigationState {
  activeTab: ActiveTab;
  requestId: string | null;
  requestSearch: string;
  requestModelFilter: string;
  chatGroupBy: ChatGroupBy;
  selectedChatGroup: string | null;
}

export const DEFAULT_NAVIGATION: NavigationState = {
  activeTab: 'requests',
  requestId: null,
  requestSearch: '',
  requestModelFilter: '',
  chatGroupBy: 'system_prompt',
  selectedChatGroup: null,
};

export function parseChatGroupBy(value: string | null): ChatGroupBy {
  if (value === 'client' || value === 'model' || value === 'system_prompt' || value === 'system_prompt_first_user') {
    return value;
  }

  return DEFAULT_NAVIGATION.chatGroupBy;
}

export function readNavigationFromLocation(location: Location = window.location): NavigationState {
  const params = new URLSearchParams(location.search);
  return {
    activeTab: params.get('tab') === 'chat' ? 'chat' : 'requests',
    requestId: params.get('request'),
    requestSearch: params.get('q') ?? '',
    requestModelFilter: params.get('model') ?? '',
    chatGroupBy: parseChatGroupBy(params.get('groupBy')),
    selectedChatGroup: params.get('group'),
  };
}

export function buildNavigationUrl(
  state: NavigationState,
  location: Location = window.location,
): string {
  const params = new URLSearchParams();

  if (state.activeTab === 'chat') {
    params.set('tab', 'chat');
    if (state.chatGroupBy !== DEFAULT_NAVIGATION.chatGroupBy) {
      params.set('groupBy', state.chatGroupBy);
    }
    if (state.selectedChatGroup) {
      params.set('group', state.selectedChatGroup);
    }
  } else {
    if (state.requestSearch) {
      params.set('q', state.requestSearch);
    }
    if (state.requestModelFilter) {
      params.set('model', state.requestModelFilter);
    }
    if (state.requestId) {
      params.set('request', state.requestId);
    }
  }

  const search = params.toString();
  return `${location.pathname}${search ? `?${search}` : ''}${location.hash}`;
}