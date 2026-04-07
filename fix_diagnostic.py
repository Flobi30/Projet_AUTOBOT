import re

with open('Diagnostic.tsx', 'r') as f:
    content = f.read()

# Remplacer SkeletonDiagnostic par le spinner uniforme
old_skeleton = '''const SkeletonDiagnostic = () => (
  <div className="p-4 lg:p-8 bg-gray-900 min-h-screen">
    <div className="mb-6 lg:mb-8 mt-16 lg:mt-0">
      <Skeleton width={350} height={40} baseColor="#1a1a1a" highlightColor="#2a2a2a" />
      <Skeleton width={400} height={20} baseColor="#1a1a1a" highlightColor="#2a2a2a" className="mt-2" />
    </div>
    <div className="grid grid-cols-1 md:grid-cols-3 gap-4 lg:gap-6 mb-6 lg:mb-8">
      <Skeleton height={120} baseColor="#1a1a1a" highlightColor="#2a2a2a" />
      <Skeleton height={120} baseColor="#1a1a1a" highlightColor="#2a2a2a" />
      <Skeleton height={120} baseColor="#1a1a1a" highlightColor="#2a2a2a" />
    </div>
    <Skeleton height={300} baseColor="#1a1a1a" highlightColor="#2a2a2a" />
  </div>
);'''

new_skeleton = '''const SkeletonDiagnostic = () => (
  <div className="p-8 bg-gray-900 min-h-screen flex items-center justify-center">
    <div className="flex flex-col items-center">
      <div className="w-12 h-12 border-4 border-emerald-500/30 border-t-emerald-500 rounded-full animate-spin"></div>
      <span className="mt-4 text-emerald-400">Chargement...</span>
    </div>
  </div>
);'''

if old_skeleton in content:
    content = content.replace(old_skeleton, new_skeleton)
    print('✅ Animation Diagnostic corrigée (Skeleton -> Spinner)')
else:
    print('⚠️ Pattern non trouvé, vérification...')
    # Essayer avec un pattern plus souple
    import re
    pattern = r'const SkeletonDiagnostic = \(\) => \([^)]+\);'
    if re.search(pattern, content, re.DOTALL):
        content = re.sub(pattern, new_skeleton, content, flags=re.DOTALL)
        print('✅ Animation Diagnostic corrigée (avec regex)')
    else:
        print('❌ Pattern SkeletonDiagnostic introuvable')

with open('Diagnostic.tsx', 'w') as f:
    f.write(content)
