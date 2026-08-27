import { View, type StyleProp, type ViewStyle } from 'react-native';

import { spacing } from '@/theme';

type Props = {
  children: React.ReactNode;
  direction?: 'column' | 'row';
  /** Gap in spacing units, not pixels. */
  gap?: number;
  align?: 'flex-start' | 'center' | 'flex-end' | 'stretch';
  justify?: 'flex-start' | 'center' | 'flex-end' | 'space-between';
  wrap?: boolean;
  style?: StyleProp<ViewStyle>;
  testID?: string;
};

/** Layout in multiples of the design's spacing unit. */
export function Stack({
  children,
  direction = 'column',
  gap = 0,
  align,
  justify,
  wrap = false,
  style,
  testID,
}: Props) {
  return (
    <View
      testID={testID}
      style={[
        {
          flexDirection: direction,
          gap: spacing(gap),
          alignItems: align,
          justifyContent: justify,
          flexWrap: wrap ? 'wrap' : 'nowrap',
        },
        style,
      ]}
    >
      {children}
    </View>
  );
}
