<?php
/**
 * Removes the plugin's settings when it is deleted from WordPress.
 */
if ( ! defined( 'WP_UNINSTALL_PLUGIN' ) ) {
	exit;
}
delete_option( 'nimmi_ai_chat' );
