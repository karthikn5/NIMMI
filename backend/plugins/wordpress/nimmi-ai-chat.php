<?php
/**
 * Plugin Name:       Nimmi AI Chat
 * Plugin URI:        https://nimmiai.in
 * Description:       Adds your Nimmi AI assistant to every page of this site. It answers visitors, collects their details and hands over to your team.
 * Version:           1.0.0
 * Requires at least: 5.2
 * Requires PHP:      7.2
 * Author:            Nimmi AI
 * Author URI:        https://nimmiai.in
 * License:           GPL-2.0-or-later
 * License URI:       https://www.gnu.org/licenses/gpl-2.0.html
 * Text Domain:       nimmi-ai-chat
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

define( 'NIMMI_AI_CHAT_VERSION', '1.0.0' );

/**
 * Settings this copy of the plugin was downloaded with (from the Nimmi dashboard).
 */
function nimmi_ai_chat_defaults() {
	return array(
		'enabled'       => 1,
		'bot_id'        => '{{BOT_ID}}',
		'api_url'       => '{{API_URL}}',
		'dashboard_url' => '{{DASHBOARD_URL}}',
	);
}

function nimmi_ai_chat_settings() {
	return wp_parse_args( (array) get_option( 'nimmi_ai_chat', array() ), nimmi_ai_chat_defaults() );
}

register_activation_hook( __FILE__, 'nimmi_ai_chat_activate' );
function nimmi_ai_chat_activate() {
	if ( false === get_option( 'nimmi_ai_chat' ) ) {
		add_option( 'nimmi_ai_chat', nimmi_ai_chat_defaults() );
	}
}

/* ---------- On the site: load the chat widget in the footer ---------- */

add_action( 'wp_enqueue_scripts', 'nimmi_ai_chat_enqueue' );
function nimmi_ai_chat_enqueue() {
	$settings = nimmi_ai_chat_settings();
	if ( empty( $settings['enabled'] ) || empty( $settings['bot_id'] ) || empty( $settings['api_url'] ) ) {
		return;
	}
	wp_enqueue_script( 'nimmi-ai-chat', untrailingslashit( $settings['api_url'] ) . '/static/nimmi-widget.js', array(), NIMMI_AI_CHAT_VERSION, true );
}

add_filter( 'script_loader_tag', 'nimmi_ai_chat_script_tag', 10, 3 );
function nimmi_ai_chat_script_tag( $tag, $handle, $src ) {
	if ( 'nimmi-ai-chat' !== $handle ) {
		return $tag;
	}
	$settings = nimmi_ai_chat_settings();
	$attributes = sprintf(
		' data-bot-id="%s" data-api-url="%s"',
		esc_attr( $settings['bot_id'] ),
		esc_attr( untrailingslashit( $settings['api_url'] ) )
	);
	if ( ! empty( $settings['dashboard_url'] ) ) {
		$attributes .= sprintf( ' data-dashboard-url="%s"', esc_attr( untrailingslashit( $settings['dashboard_url'] ) ) );
	}
	return sprintf( '<script src="%s" id="nimmi-ai-chat-js"%s async></script>' . "\n", esc_url( $src ), $attributes );
}

/* ---------- In wp-admin: Settings > Nimmi AI Chat ---------- */

add_action( 'admin_menu', 'nimmi_ai_chat_menu' );
function nimmi_ai_chat_menu() {
	add_options_page(
		__( 'Nimmi AI Chat', 'nimmi-ai-chat' ),
		__( 'Nimmi AI Chat', 'nimmi-ai-chat' ),
		'manage_options',
		'nimmi-ai-chat',
		'nimmi_ai_chat_page'
	);
}

add_action( 'admin_init', 'nimmi_ai_chat_register' );
function nimmi_ai_chat_register() {
	register_setting( 'nimmi_ai_chat', 'nimmi_ai_chat', array( 'sanitize_callback' => 'nimmi_ai_chat_sanitize' ) );
}

function nimmi_ai_chat_sanitize( $input ) {
	$input    = (array) $input;
	$previous = nimmi_ai_chat_settings();
	$clean    = $previous;

	$clean['enabled'] = empty( $input['enabled'] ) ? 0 : 1;

	$bot_id = isset( $input['bot_id'] ) ? strtolower( trim( sanitize_text_field( $input['bot_id'] ) ) ) : '';
	if ( preg_match( '/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/', $bot_id ) ) {
		$clean['bot_id'] = $bot_id;
	} else {
		add_settings_error( 'nimmi_ai_chat', 'bot_id', __( 'That assistant ID is not valid. Copy it from Add to website in your Nimmi dashboard.', 'nimmi-ai-chat' ) );
	}

	foreach ( array( 'api_url', 'dashboard_url' ) as $key ) {
		if ( isset( $input[ $key ] ) ) {
			$url = esc_url_raw( trim( $input[ $key ] ), array( 'https', 'http' ) );
			if ( '' !== $url || 'dashboard_url' === $key ) {
				$clean[ $key ] = untrailingslashit( $url );
			}
		}
	}
	return $clean;
}

add_filter( 'plugin_action_links_' . plugin_basename( __FILE__ ), 'nimmi_ai_chat_action_links' );
function nimmi_ai_chat_action_links( $links ) {
	$url = admin_url( 'options-general.php?page=nimmi-ai-chat' );
	array_unshift( $links, '<a href="' . esc_url( $url ) . '">' . esc_html__( 'Settings', 'nimmi-ai-chat' ) . '</a>' );
	return $links;
}

function nimmi_ai_chat_page() {
	if ( ! current_user_can( 'manage_options' ) ) {
		return;
	}
	$settings = nimmi_ai_chat_settings();
	?>
	<div class="wrap">
		<h1><?php esc_html_e( 'Nimmi AI Chat', 'nimmi-ai-chat' ); ?></h1>
		<p><?php esc_html_e( 'Your assistant appears as a chat button on every page of this site. Change what it says and knows in your Nimmi dashboard; this page only connects it.', 'nimmi-ai-chat' ); ?></p>
		<form method="post" action="options.php">
			<?php settings_fields( 'nimmi_ai_chat' ); ?>
			<table class="form-table" role="presentation">
				<tr>
					<th scope="row"><?php esc_html_e( 'Chat button', 'nimmi-ai-chat' ); ?></th>
					<td>
						<label>
							<input type="checkbox" name="nimmi_ai_chat[enabled]" value="1" <?php checked( ! empty( $settings['enabled'] ) ); ?> />
							<?php esc_html_e( 'Show the assistant on this site', 'nimmi-ai-chat' ); ?>
						</label>
					</td>
				</tr>
				<tr>
					<th scope="row"><label for="nimmi-ai-chat-bot"><?php esc_html_e( 'Assistant ID', 'nimmi-ai-chat' ); ?></label></th>
					<td>
						<input type="text" id="nimmi-ai-chat-bot" class="regular-text code" name="nimmi_ai_chat[bot_id]" value="<?php echo esc_attr( $settings['bot_id'] ); ?>" />
						<p class="description"><?php esc_html_e( 'Filled in for you. To show a different assistant, paste its ID from Add to website in the Nimmi dashboard.', 'nimmi-ai-chat' ); ?></p>
					</td>
				</tr>
				<tr>
					<th scope="row"><label for="nimmi-ai-chat-api"><?php esc_html_e( 'Nimmi server', 'nimmi-ai-chat' ); ?></label></th>
					<td>
						<input type="url" id="nimmi-ai-chat-api" class="regular-text code" name="nimmi_ai_chat[api_url]" value="<?php echo esc_attr( $settings['api_url'] ); ?>" />
						<input type="hidden" name="nimmi_ai_chat[dashboard_url]" value="<?php echo esc_attr( $settings['dashboard_url'] ); ?>" />
						<p class="description"><?php esc_html_e( 'Leave as it is unless Nimmi support asks you to change it.', 'nimmi-ai-chat' ); ?></p>
					</td>
				</tr>
			</table>
			<?php submit_button(); ?>
		</form>
	</div>
	<?php
}
