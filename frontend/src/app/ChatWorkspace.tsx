import { ChatView } from '../components/ChatView/ChatView';
import type { NavigationState } from './navigation';

interface ChatWorkspaceProps {
  navigation: NavigationState;
  updateNavigation: (
    updater: NavigationState | ((current: NavigationState) => NavigationState),
  ) => void;
}

export function ChatWorkspace({ navigation, updateNavigation }: ChatWorkspaceProps) {
  return (
    <div style={{ flex: 1, overflow: 'hidden' }}>
      <ChatView
        groupBy={navigation.chatGroupBy}
        selectedGroup={navigation.selectedChatGroup}
        onGroupByChange={groupBy => {
          updateNavigation(current => ({
            ...current,
            activeTab: 'chat',
            chatGroupBy: groupBy,
            selectedChatGroup: null,
          }));
        }}
        onSelectGroup={groupKey => {
          updateNavigation(current => ({ ...current, activeTab: 'chat', selectedChatGroup: groupKey }));
        }}
      />
    </div>
  );
}