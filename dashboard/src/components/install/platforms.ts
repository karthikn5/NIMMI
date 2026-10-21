/**
 * Every place an assistant can be added: the steps and ready-to-paste code for each, filled in
 * with the assistant's ID and Nimmi's addresses. Websites load the chat widget script; phone apps
 * show the chat page full screen in a web view (with the microphone allowed for voice input).
 */

export type Ctx = { botId: string; botName: string; api: string; dashboard: string };
export type Block = { label: string; code: string };
export type Group = "Website" | "Mobile app" | "Hosted by Nimmi";
export type Platform = {
    id: string;
    group: Group;
    label: string;
    tag?: string;
    title: string;
    summary: string;
    steps: string[];
    blocks: (c: Ctx) => Block[];
    download?: "wordpress";
    link?: { href: string; label: string };
    needsPlan: boolean;
};

const PRODUCTION_DASHBOARD = "https://nimmiai.in";

const scriptUrl = (c: Ctx) => `${c.api}/static/nimmi-widget.js`;
const appUrl = (c: Ctx) => `${c.dashboard}/widget/${c.botId}?app=1`;

export function htmlTag(c: Ctx) {
    const lines = [
        "<!-- Nimmi AI assistant -->",
        "<script",
        `  src="${scriptUrl(c)}"`,
        `  data-bot-id="${c.botId}"`,
        `  data-api-url="${c.api}"`,
        ...(c.dashboard !== PRODUCTION_DASHBOARD ? [`  data-dashboard-url="${c.dashboard}"`] : []),
        "  async",
        "></script>",
    ];
    return lines.join("\n");
}

const scriptJs = (c: Ctx, indent: string) => [
    `if (!document.getElementById("nimmi-ai-chat")) {`,
    `  const script = document.createElement("script");`,
    `  script.id = "nimmi-ai-chat";`,
    `  script.src = "${scriptUrl(c)}";`,
    `  script.async = true;`,
    `  script.dataset.botId = "${c.botId}";`,
    `  script.dataset.apiUrl = "${c.api}";`,
    ...(c.dashboard !== PRODUCTION_DASHBOARD ? [`  script.dataset.dashboardUrl = "${c.dashboard}";`] : []),
    `  document.body.appendChild(script);`,
    `}`,
].map((l) => indent + l).join("\n");

const MANIFEST = `<!-- AndroidManifest.xml, inside <manifest> -->
<uses-permission android:name="android.permission.INTERNET" />
<!-- Only if you want customers to speak to the assistant (the mic button) -->
<uses-permission android:name="android.permission.RECORD_AUDIO" />

<!-- inside <application> -->
<activity android:name=".NimmiChatActivity" android:label="Chat with us" />`;

export const PLATFORMS: Platform[] = [
    /* ---------------- websites ---------------- */
    {
        id: "html", group: "Website", label: "Any website", tag: "HTML", needsPlan: true,
        title: "Add it to any website",
        summary: "One line of code shows the chat button on every page. Works with hand-made sites and with Angular, Svelte, Laravel, Django, PHP and others.",
        steps: [
            "Copy the code below.",
            "Paste it just before the closing </body> tag of your site's pages (or of the shared footer or layout file).",
            "Publish your site and refresh it. The chat button appears in the corner.",
        ],
        blocks: (c) => [{ label: "HTML", code: htmlTag(c) }],
    },
    {
        id: "wordpress", group: "Website", label: "WordPress", tag: "Plugin", needsPlan: true, download: "wordpress",
        title: "Add it to WordPress",
        summary: "Download a plugin that's already connected to this assistant. No code to copy.",
        steps: [
            "Download the plugin (nimmi-ai-chat.zip). Don't unzip it.",
            "In WordPress, go to Plugins, Add New Plugin, then Upload Plugin.",
            "Choose the .zip file, select Install Now, then Activate Plugin.",
            "Visit your site: the chat button is on every page. To turn it off later, go to Settings, Nimmi AI Chat.",
        ],
        blocks: (c) => [{ label: "Can't upload plugins? (WordPress.com free plans) Paste this with a header and footer code plugin instead", code: htmlTag(c) }],
    },
    {
        id: "builders", group: "Website", label: "Shopify, Wix and others", tag: "No code", needsPlan: true,
        title: "Add it with a website builder",
        summary: "Most builders have a place for custom code that runs on every page. Paste the code there.",
        steps: [
            "Shopify: Online Store, Themes, the three dots, Edit code. Open layout/theme.liquid and paste the code just before </body>. Save.",
            "Wix: Settings, Custom code (under Development & integrations), Add Custom Code. Paste the code, choose All pages and Body - end. Needs a paid Wix plan with a domain.",
            "Webflow: Site settings, Custom code, Footer code. Paste, save and publish.",
            "Squarespace: Settings, Developer tools, Code injection, Footer. Paste and save.",
            "Google Tag Manager: Tags, New, Custom HTML. Paste the code, set the trigger to All Pages, then Submit and publish.",
        ],
        blocks: (c) => [{ label: "Code to paste", code: htmlTag(c) }],
    },
    {
        id: "react", group: "Website", label: "React", tag: "JS / TS", needsPlan: true,
        title: "Add it to a React app",
        summary: "A small component that loads the chat once. Works with Vite, Create React App and other React setups.",
        steps: [
            "Create NimmiChat.tsx (or .jsx) with the code below.",
            "Render <NimmiChat /> once, for example in your App component.",
        ],
        blocks: (c) => [{
            label: "NimmiChat.tsx",
            code: `import { useEffect } from "react";

/** Shows the Nimmi AI chat button. Render it once, e.g. in App. */
export default function NimmiChat() {
  useEffect(() => {
${scriptJs(c, "    ")}
  }, []);
  return null;
}`,
        }],
    },
    {
        id: "nextjs", group: "Website", label: "Next.js", tag: "App Router", needsPlan: true,
        title: "Add it to a Next.js site",
        summary: "Use Next.js's Script component in your root layout so the chat is on every page.",
        steps: [
            "Open app/layout.tsx (Pages Router: pages/_app.tsx).",
            "Import Script and add the tag inside <body>, after {children}.",
        ],
        blocks: (c) => [{
            label: "app/layout.tsx",
            code: `import Script from "next/script";

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        {children}
        <Script
          src="${scriptUrl(c)}"
          data-bot-id="${c.botId}"
          data-api-url="${c.api}"${c.dashboard !== PRODUCTION_DASHBOARD ? `\n          data-dashboard-url="${c.dashboard}"` : ""}
          strategy="afterInteractive"
        />
      </body>
    </html>
  );
}`,
        }],
    },
    {
        id: "vue", group: "Website", label: "Vue / Nuxt", tag: "JS / TS", needsPlan: true,
        title: "Add it to a Vue or Nuxt app",
        summary: "Load the chat once when your app starts.",
        steps: [
            "Vue: add the code to src/main.ts (or main.js), after app.mount(\"#app\").",
            "Nuxt: create plugins/nimmi-chat.client.ts and put the code inside defineNuxtPlugin(() => { ... }).",
        ],
        blocks: (c) => [{ label: "src/main.ts", code: `// After app.mount("#app"):\n${scriptJs(c, "")}` }],
    },

    /* ---------------- phone apps ---------------- */
    {
        id: "android-kotlin", group: "Mobile app", label: "Android (Kotlin)", tag: "Native", needsPlan: true,
        title: "Add it to an Android app (Kotlin)",
        summary: "A screen that shows the chat, with the microphone working for voice input. Open it from a \"Chat with us\" button.",
        steps: [
            "Add the permissions and the activity to AndroidManifest.xml.",
            "Create NimmiChatActivity.kt with the code below (it needs androidx.appcompat, which new projects include).",
            "Open the chat from any button: startActivity(Intent(this, NimmiChatActivity::class.java)).",
        ],
        blocks: (c) => [
            { label: "AndroidManifest.xml", code: MANIFEST },
            {
                label: "NimmiChatActivity.kt",
                code: `import android.Manifest
import android.annotation.SuppressLint
import android.content.pm.PackageManager
import android.os.Bundle
import android.webkit.PermissionRequest
import android.webkit.WebChromeClient
import android.webkit.WebView
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat

class NimmiChatActivity : AppCompatActivity() {
    private var pendingRequest: PermissionRequest? = null

    // Asks for the microphone the first time the customer taps the mic button.
    private val askMic = registerForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
        pendingRequest?.let { if (granted) it.grant(arrayOf(PermissionRequest.RESOURCE_AUDIO_CAPTURE)) else it.deny() }
        pendingRequest = null
    }

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val webView = WebView(this)
        webView.settings.javaScriptEnabled = true
        webView.settings.domStorageEnabled = true
        webView.settings.mediaPlaybackRequiresUserGesture = false
        webView.webChromeClient = object : WebChromeClient() {
            override fun onPermissionRequest(request: PermissionRequest) {
                when {
                    PermissionRequest.RESOURCE_AUDIO_CAPTURE !in request.resources -> request.deny()
                    ContextCompat.checkSelfPermission(this@NimmiChatActivity, Manifest.permission.RECORD_AUDIO) ==
                        PackageManager.PERMISSION_GRANTED -> request.grant(arrayOf(PermissionRequest.RESOURCE_AUDIO_CAPTURE))
                    else -> { pendingRequest = request; askMic.launch(Manifest.permission.RECORD_AUDIO) }
                }
            }
        }
        setContentView(webView)
        webView.loadUrl(CHAT_URL)
    }

    companion object {
        const val CHAT_URL = "${appUrl(c)}"
    }
}`,
            },
        ],
    },
    {
        id: "android-java", group: "Mobile app", label: "Android (Java)", tag: "Native", needsPlan: true,
        title: "Add it to an Android app (Java)",
        summary: "A screen that shows the chat, with the microphone working for voice input. Open it from a \"Chat with us\" button.",
        steps: [
            "Add the permissions and the activity to AndroidManifest.xml.",
            "Create NimmiChatActivity.java with the code below (it needs androidx.appcompat, which new projects include).",
            "Open the chat from any button: startActivity(new Intent(this, NimmiChatActivity.class));",
        ],
        blocks: (c) => [
            { label: "AndroidManifest.xml", code: MANIFEST },
            {
                label: "NimmiChatActivity.java",
                code: `import android.Manifest;
import android.annotation.SuppressLint;
import android.content.pm.PackageManager;
import android.os.Bundle;
import android.webkit.PermissionRequest;
import android.webkit.WebChromeClient;
import android.webkit.WebSettings;
import android.webkit.WebView;
import androidx.activity.result.ActivityResultLauncher;
import androidx.activity.result.contract.ActivityResultContracts;
import androidx.appcompat.app.AppCompatActivity;
import androidx.core.content.ContextCompat;
import java.util.Arrays;

public class NimmiChatActivity extends AppCompatActivity {
    private static final String CHAT_URL = "${appUrl(c)}";
    private static final String[] MIC = { PermissionRequest.RESOURCE_AUDIO_CAPTURE };
    private PermissionRequest pendingRequest;

    // Asks for the microphone the first time the customer taps the mic button.
    private final ActivityResultLauncher<String> askMic =
            registerForActivityResult(new ActivityResultContracts.RequestPermission(), granted -> {
                if (pendingRequest == null) return;
                if (granted) pendingRequest.grant(MIC); else pendingRequest.deny();
                pendingRequest = null;
            });

    @SuppressLint("SetJavaScriptEnabled")
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        WebView webView = new WebView(this);
        WebSettings settings = webView.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setMediaPlaybackRequiresUserGesture(false);
        webView.setWebChromeClient(new WebChromeClient() {
            @Override
            public void onPermissionRequest(PermissionRequest request) {
                if (!Arrays.asList(request.getResources()).contains(PermissionRequest.RESOURCE_AUDIO_CAPTURE)) {
                    request.deny();
                } else if (ContextCompat.checkSelfPermission(NimmiChatActivity.this, Manifest.permission.RECORD_AUDIO)
                        == PackageManager.PERMISSION_GRANTED) {
                    request.grant(MIC);
                } else {
                    pendingRequest = request;
                    askMic.launch(Manifest.permission.RECORD_AUDIO);
                }
            }
        });
        setContentView(webView);
        webView.loadUrl(CHAT_URL);
    }
}`,
            },
        ],
    },
    {
        id: "ios-swift", group: "Mobile app", label: "iPhone and iPad (Swift)", tag: "Native", needsPlan: true,
        title: "Add it to an iOS app (Swift)",
        summary: "A SwiftUI view that shows the chat, with the microphone working for voice input (iOS 15 and later).",
        steps: [
            "In Info.plist, add Privacy - Microphone Usage Description (only if you want voice input).",
            "Create NimmiChatView.swift with the code below.",
            "Show it from a button, for example .sheet(isPresented: $showChat) { NimmiChatView() }. UIKit apps can present UIHostingController(rootView: NimmiChatView()).",
        ],
        blocks: (c) => [
            {
                label: "Info.plist",
                code: `<key>NSMicrophoneUsageDescription</key>
<string>So you can speak to our assistant instead of typing.</string>`,
            },
            {
                label: "NimmiChatView.swift",
                code: `import SwiftUI
import WebKit

/// The Nimmi AI chat, full screen.
struct NimmiChatView: UIViewRepresentable {
    private let url = URL(string: "${appUrl(c)}")!

    func makeCoordinator() -> Coordinator { Coordinator() }

    func makeUIView(context: Context) -> WKWebView {
        let configuration = WKWebViewConfiguration()
        configuration.allowsInlineMediaPlayback = true
        configuration.mediaTypesRequiringUserActionForPlayback = []
        let webView = WKWebView(frame: .zero, configuration: configuration)
        webView.uiDelegate = context.coordinator
        webView.load(URLRequest(url: url))
        return webView
    }

    func updateUIView(_ webView: WKWebView, context: Context) {}

    final class Coordinator: NSObject, WKUIDelegate {
        // Lets the chat use the microphone; iOS still asks the customer once.
        @available(iOS 15.0, *)
        func webView(_ webView: WKWebView,
                     requestMediaCapturePermissionFor origin: WKSecurityOrigin,
                     initiatedByFrame frame: WKFrameInfo,
                     type: WKMediaCaptureType,
                     decisionHandler: @escaping (WKPermissionDecision) -> Void) {
            decisionHandler(type == .microphone ? .grant : .deny)
        }
    }
}`,
            },
        ],
    },
    {
        id: "flutter", group: "Mobile app", label: "Flutter", tag: "Dart", needsPlan: true,
        title: "Add it to a Flutter app",
        summary: "One screen for Android and iOS, using the official webview_flutter package.",
        steps: [
            "Add webview_flutter to pubspec.yaml and run flutter pub get.",
            "Create nimmi_chat_screen.dart with the code below.",
            "For voice input, add the Android microphone permission (RECORD_AUDIO in AndroidManifest.xml) and NSMicrophoneUsageDescription in ios/Runner/Info.plist.",
            "Open it from a button: Navigator.push(context, MaterialPageRoute(builder: (_) => const NimmiChatScreen()));",
        ],
        blocks: (c) => [
            { label: "pubspec.yaml", code: `dependencies:\n  webview_flutter: ^4.10.0` },
            {
                label: "lib/nimmi_chat_screen.dart",
                code: `import 'package:flutter/material.dart';
import 'package:webview_flutter/webview_flutter.dart';

/// The Nimmi AI chat, full screen.
class NimmiChatScreen extends StatefulWidget {
  const NimmiChatScreen({super.key});

  @override
  State<NimmiChatScreen> createState() => _NimmiChatScreenState();
}

class _NimmiChatScreenState extends State<NimmiChatScreen> {
  late final WebViewController _controller = WebViewController(
    // Lets the chat use the microphone for voice input.
    onPermissionRequest: (request) => request.grant(),
  )
    ..setJavaScriptMode(JavaScriptMode.unrestricted)
    ..loadRequest(Uri.parse('${appUrl(c)}'));

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Chat with us')),
      body: SafeArea(child: WebViewWidget(controller: _controller)),
    );
  }
}`,
            },
        ],
    },
    {
        id: "react-native", group: "Mobile app", label: "React Native", tag: "Expo / CLI", needsPlan: true,
        title: "Add it to a React Native app",
        summary: "One screen for Android and iOS, using react-native-webview.",
        steps: [
            "Install the web view: npx expo install react-native-webview (or npm install react-native-webview, then cd ios && pod install).",
            "Create NimmiChatScreen.tsx with the code below and add it to your navigator.",
            "For voice input, add RECORD_AUDIO to AndroidManifest.xml and NSMicrophoneUsageDescription to Info.plist (Expo: under android.permissions and ios.infoPlist in app.json).",
        ],
        blocks: (c) => [
            {
                label: "NimmiChatScreen.tsx",
                code: `import { SafeAreaView } from "react-native";
import { WebView } from "react-native-webview";

/** The Nimmi AI chat, full screen. */
export default function NimmiChatScreen() {
  return (
    <SafeAreaView style={{ flex: 1 }}>
      <WebView
        source={{ uri: "${appUrl(c)}" }}
        javaScriptEnabled
        domStorageEnabled
        allowsInlineMediaPlayback
        mediaPlaybackRequiresUserAction={false}
        mediaCapturePermissionGrantType="grant"
      />
    </SafeAreaView>
  );
}`,
            },
        ],
    },

    /* ---------------- hosted ---------------- */
    {
        id: "nimmi-site", group: "Hosted by Nimmi", label: "Publish a website", tag: "No code", needsPlan: false,
        title: "Publish your website on Nimmi",
        summary: "Don't have a website, or don't want to touch its code? Upload it to Nimmi, get a free web address, and switch this assistant on for every page in one click.",
        steps: [
            "Open Deployments and choose New deployment.",
            "Drop your site's folder or a .zip, or import it from GitHub.",
            "On the site's page, choose this assistant under Assistant on this site.",
        ],
        blocks: () => [],
        link: { href: "/dashboard/deployments", label: "Open Deployments" },
    },
];

export const GROUPS: Group[] = ["Website", "Mobile app", "Hosted by Nimmi"];
