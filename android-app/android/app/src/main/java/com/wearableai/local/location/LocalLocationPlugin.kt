package com.wearableai.local.location

import android.Manifest
import android.location.Location
import com.getcapacitor.JSObject
import com.getcapacitor.PermissionState
import com.getcapacitor.Plugin
import com.getcapacitor.PluginCall
import com.getcapacitor.PluginMethod
import com.getcapacitor.annotation.CapacitorPlugin
import com.getcapacitor.annotation.Permission
import com.getcapacitor.annotation.PermissionCallback
import com.google.android.gms.location.CurrentLocationRequest
import com.google.android.gms.location.FusedLocationProviderClient
import com.google.android.gms.location.LocationServices
import com.google.android.gms.location.Priority
import com.google.android.gms.tasks.CancellationTokenSource

@CapacitorPlugin(
    name = "LocalLocation",
    permissions = [
        Permission(
            alias = "location",
            strings = [Manifest.permission.ACCESS_COARSE_LOCATION, Manifest.permission.ACCESS_FINE_LOCATION]
        )
    ]
)
class LocalLocationPlugin : Plugin() {
    private lateinit var locations: FusedLocationProviderClient

    override fun load() {
        locations = LocationServices.getFusedLocationProviderClient(context)
    }

    @PluginMethod
    fun getCurrentCoordinates(call: PluginCall) {
        if (getPermissionState("location") != PermissionState.GRANTED) {
            requestPermissionForAlias("location", call, "locationPermissionCallback")
            return
        }
        fetch(call, proximity = false)
    }

    @PluginMethod
    fun getProximityState(call: PluginCall) {
        if (getPermissionState("location") != PermissionState.GRANTED) {
            call.resolve(JSObject().apply {
                put("available", false)
                put("reason", "permission_required")
                put("withinRadius", false)
            })
            return
        }
        fetch(call, proximity = true)
    }

    @PermissionCallback
    private fun locationPermissionCallback(call: PluginCall) {
        if (getPermissionState("location") == PermissionState.GRANTED) fetch(call, proximity = false)
        else call.reject("Location permission is required.", "LOCATION_PERMISSION_DENIED")
    }

    private fun fetch(call: PluginCall, proximity: Boolean) {
        val request = CurrentLocationRequest.Builder()
            .setPriority(Priority.PRIORITY_BALANCED_POWER_ACCURACY)
            .setDurationMillis((call.getLong("timeoutMs") ?: 10_000L).coerceIn(1_000L, 30_000L))
            .setMaxUpdateAgeMillis((call.getLong("maxAgeMs") ?: 30_000L).coerceIn(0L, 300_000L))
            .build()
        val cancellation = CancellationTokenSource()
        locations.getCurrentLocation(request, cancellation.token)
            .addOnSuccessListener { location ->
                if (location == null) {
                    call.reject("No current location is available.", "LOCATION_UNAVAILABLE")
                } else if (proximity) {
                    resolveProximity(call, location)
                } else {
                    call.resolve(coordinates(location))
                }
            }
            .addOnFailureListener { error ->
                call.reject(error.message ?: "Location lookup failed.", "LOCATION_FAILED", error)
            }
    }

    private fun resolveProximity(call: PluginCall, current: Location) {
        val latitude = call.getDouble("latitude")
        val longitude = call.getDouble("longitude")
        if (latitude == null || longitude == null || latitude !in -90.0..90.0 || longitude !in -180.0..180.0) {
            call.reject("A valid target latitude and longitude are required.", "INVALID_COORDINATES")
            return
        }
        val radius = (call.getDouble("radiusMeters") ?: 200.0).coerceIn(25.0, 10_000.0)
        val result = FloatArray(1)
        Location.distanceBetween(current.latitude, current.longitude, latitude, longitude, result)
        call.resolve(JSObject().apply {
            put("available", true)
            put("withinRadius", result[0] <= radius)
            put("distanceMeters", result[0].toDouble())
            put("radiusMeters", radius)
            put("accuracyMeters", current.accuracy.toDouble())
            put("timestamp", current.time)
        })
    }

    private fun coordinates(location: Location) = JSObject().apply {
        put("latitude", location.latitude)
        put("longitude", location.longitude)
        put("accuracyMeters", location.accuracy.toDouble())
        put("timestamp", location.time)
    }
}
