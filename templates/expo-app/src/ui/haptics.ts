import * as Haptics from 'expo-haptics';
import { Platform } from 'react-native';

/**
 * Haptics mark a moment the user caused and cares about.
 *
 * Never on navigation, never on arrival, never on scroll: haptics on everything
 * are the same as haptics on nothing, except they also drain the battery.
 */

const enabled = Platform.OS === 'ios' || Platform.OS === 'android';

async function safely(run: () => Promise<void>): Promise<void> {
  if (!enabled) return;
  try {
    await run();
  } catch {
    // A device without a haptic engine must never break the interaction.
  }
}

/** A selection changed: a toggle, a segment, a picker. */
export const selection = () => safely(() => Haptics.selectionAsync());

/** A light confirmation: an item saved, added, removed. */
export const tap = () => safely(() => Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light));

/** A significant confirmation: a purchase, a submission. */
export const success = () =>
  safely(() => Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success));

/** A recoverable problem the user should notice. */
export const warning = () =>
  safely(() => Haptics.notificationAsync(Haptics.NotificationFeedbackType.Warning));

/** A failure: declined, rejected, refused. */
export const error = () =>
  safely(() => Haptics.notificationAsync(Haptics.NotificationFeedbackType.Error));

export const haptics = { selection, tap, success, warning, error };
