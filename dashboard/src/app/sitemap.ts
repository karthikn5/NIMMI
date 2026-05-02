import { MetadataRoute } from 'next';

export default function sitemap(): MetadataRoute.Sitemap {
  const baseUrl = 'https://nimmiai.in';

  // List of public routes
  const routes = [
    '',
    '/auth/login',
    '/auth/signup',
    '/blog',
    '/blog/how-to-build-custom-ai-chatbot-2026',
    '/blog/ai-chatbot-vs-live-chat-india',
    '/blog/calculating-chatbot-roi',
  ];

  return routes.map((route) => ({
    url: `${baseUrl}${route}`,
    lastModified: new Date(),
    changeFrequency: route === '' ? 'daily' : 'monthly',
    priority: route === '' ? 1 : 0.8,
  }));
}
