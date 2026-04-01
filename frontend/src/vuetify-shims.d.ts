declare module 'vuetify/styles' {
  const styles: string
  export default styles
}

declare module 'vuetify/iconsets/mdi' {
  import type { IconSet, IconAliases } from 'vuetify'
  export const aliases: IconAliases
  export const mdi: IconSet
}
