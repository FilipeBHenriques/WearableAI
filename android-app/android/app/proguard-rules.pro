# Keep native plugin entry points discovered by Capacitor annotations.
-keep @com.getcapacitor.annotation.CapacitorPlugin class * { *; }
-keepclasseswithmembernames class * {
    native <methods>;
}
