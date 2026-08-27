import { Animated, Pressable, StyleSheet, View } from 'react-native';

import { MIN_TOUCH_TARGET, spacing, useTheme } from '@/theme';

import { usePressScale } from './motion';
import { Text } from './text';

type Props = {
  title: string;
  subtitle?: string;
  trailing?: string;
  onPress?: () => void;
  accessibilityHint?: string;
  testID?: string;
};

/** One row of a list. Pressable when given `onPress`, plain text otherwise. */
export function ListRow({ title, subtitle, trailing, onPress, accessibilityHint, testID }: Props) {
  const theme = useTheme();
  const { scale, onPressIn, onPressOut } = usePressScale(0.99);

  const body = (
    <View style={[styles.row, { borderBottomColor: theme.border }]}>
      <View style={styles.text}>
        <Text variant="bodyStrong" numberOfLines={1}>
          {title}
        </Text>
        {subtitle ? (
          <Text variant="caption" tone="muted" numberOfLines={1}>
            {subtitle}
          </Text>
        ) : null}
      </View>
      {trailing ? <Text variant="bodyStrong">{trailing}</Text> : null}
    </View>
  );

  if (!onPress) {
    // Composite rows announce as one element, not three fragments.
    return (
      <View testID={testID} accessible accessibilityRole="text">
        {body}
      </View>
    );
  }

  return (
    <Animated.View style={{ transform: [{ scale }] }}>
      <Pressable
        testID={testID}
        accessible
        accessibilityRole="button"
        accessibilityLabel={subtitle ? `${title}, ${subtitle}` : title}
        accessibilityHint={accessibilityHint}
        onPress={onPress}
        onPressIn={onPressIn}
        onPressOut={onPressOut}
      >
        {body}
      </Pressable>
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  row: {
    minHeight: MIN_TOUCH_TARGET + 20,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: spacing(3),
    paddingVertical: spacing(3),
    borderBottomWidth: StyleSheet.hairlineWidth,
  },
  text: { flex: 1, gap: 2 },
});
