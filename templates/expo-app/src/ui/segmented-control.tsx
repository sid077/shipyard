import { Pressable, StyleSheet, View } from 'react-native';

import { MIN_TOUCH_TARGET, radii, spacing, useTheme } from '@/theme';

import { haptics } from './haptics';
import { Text } from './text';

type Props = {
  options: { value: string; label: string }[];
  value: string;
  onChange: (value: string) => void;
  testID?: string;
};

export function SegmentedControl({ options, value, onChange, testID }: Props) {
  const theme = useTheme();
  return (
    <View
      testID={testID}
      accessibilityRole="tablist"
      style={[styles.track, { backgroundColor: theme.surface, borderRadius: radii.md }]}
    >
      {options.map((option) => {
        const selected = option.value === value;
        return (
          <Pressable
            key={option.value}
            testID={testID ? `${testID}-${option.value}` : undefined}
            accessibilityRole="tab"
            accessibilityLabel={option.label}
            accessibilityState={{ selected }}
            onPress={() => {
              void haptics.selection();
              onChange(option.value);
            }}
            style={[
              styles.segment,
              {
                backgroundColor: selected ? theme.surfaceRaised : 'transparent',
                borderRadius: radii.sm,
              },
            ]}
          >
            <Text variant={selected ? 'bodyStrong' : 'body'} tone={selected ? 'default' : 'muted'}>
              {option.label}
            </Text>
          </Pressable>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  track: { flexDirection: 'row', padding: spacing(1), gap: spacing(1) },
  segment: {
    flex: 1,
    minHeight: MIN_TOUCH_TARGET,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: spacing(3),
  },
});
