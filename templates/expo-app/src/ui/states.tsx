import { View, StyleSheet } from 'react-native';

import { spacing } from '@/theme';

import { Button } from './button';
import { Text } from './text';

type EmptyProps = {
  title: string;
  body: string;
  actionLabel?: string;
  onAction?: () => void;
  testID?: string;
};

/**
 * The first screen most users see. It teaches the product: say what belongs
 * here and how to get the first one.
 */
export function EmptyState({ title, body, actionLabel, onAction, testID }: EmptyProps) {
  return (
    <View testID={testID} style={styles.wrapper} accessible accessibilityRole="text">
      <Text variant="heading" align="center">
        {title}
      </Text>
      <Text variant="body" tone="muted" align="center">
        {body}
      </Text>
      {actionLabel && onAction ? (
        <Button label={actionLabel} onPress={onAction} variant="secondary" />
      ) : null}
    </View>
  );
}

type ErrorProps = {
  title: string;
  body: string;
  retryLabel?: string;
  onRetry?: () => void;
  testID?: string;
};

/** Says what happened, whether anything was lost, and what to do next. */
export function ErrorState({ title, body, retryLabel, onRetry, testID }: ErrorProps) {
  return (
    <View testID={testID} style={styles.wrapper}>
      <Text variant="heading" tone="danger" align="center">
        {title}
      </Text>
      <Text variant="body" tone="muted" align="center">
        {body}
      </Text>
      {retryLabel && onRetry ? <Button label={retryLabel} onPress={onRetry} /> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  wrapper: {
    gap: spacing(3),
    paddingVertical: spacing(8),
    paddingHorizontal: spacing(5),
    alignItems: 'center',
  },
});
