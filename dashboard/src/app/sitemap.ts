import { MetadataRoute } from 'next';

export default function sitemap(): MetadataRoute.Sitemap {
  const baseUrl = 'https://nimmiai.in';

  // List of public routes
  const routes = [
    '',
    '/auth/login',
    '/auth/signup',
  ];

  return routes.map((route) => ({
    url: `${baseUrl}${route}`,
    lastModified: new Date(),
    changeFrequency: route === '' ? 'daily' : 'monthly',
    priority: route === '' ? 1 : 0.8,
  }));
}
