/*
 * Chipcoin CPython wrapper for the vendored mldsa-native ML-DSA-44 backend.
 *
 * The extension intentionally exposes only deterministic core APIs. It does
 * not call mldsa-native randomized APIs and does not rely on global RNG state.
 */

#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <stdint.h>
#include <stddef.h>
#include <string.h>

#include "mldsa_native.h"

#define CHIPCOIN_MLDSA44_SEED_SIZE 32
#define CHIPCOIN_MLDSA44_DIGEST_SIZE 32

typedef int (*chipcoin_mldsa44_keypair_internal_fn)(
    uint8_t pk[MLDSA44_PUBLICKEYBYTES],
    uint8_t sk[MLDSA44_SECRETKEYBYTES],
    const uint8_t seed[CHIPCOIN_MLDSA44_SEED_SIZE]);

typedef int (*chipcoin_mldsa44_signature_internal_fn)(
    uint8_t sig[MLDSA44_BYTES], size_t *siglen,
    const uint8_t *m, size_t mlen, const uint8_t *pre, size_t prelen,
    const uint8_t rnd[CHIPCOIN_MLDSA44_SEED_SIZE],
    const uint8_t sk[MLDSA44_SECRETKEYBYTES],
    int externalmu);

typedef int (*chipcoin_mldsa44_verify_internal_fn)(
    const uint8_t *sig, size_t siglen, const uint8_t *m, size_t mlen,
    const uint8_t *pre, size_t prelen,
    const uint8_t pk[MLDSA44_PUBLICKEYBYTES],
    int externalmu);

static chipcoin_mldsa44_keypair_internal_fn api_guard_keypair =
    CHIPCOIN_MLDSA44_keypair_internal;
static chipcoin_mldsa44_signature_internal_fn api_guard_signature =
    CHIPCOIN_MLDSA44_signature_internal;
static chipcoin_mldsa44_verify_internal_fn api_guard_verify =
    CHIPCOIN_MLDSA44_verify_internal;

static PyObject *raise_value_error(const char *message)
{
    PyErr_SetString(PyExc_ValueError, message);
    return NULL;
}

static PyObject *raise_runtime_error(const char *message)
{
    PyErr_SetString(PyExc_RuntimeError, message);
    return NULL;
}

static int parse_bytes_arg(PyObject *obj, const char *name, Py_buffer *view)
{
    if (PyObject_GetBuffer(obj, view, PyBUF_SIMPLE) != 0) {
        return -1;
    }
    if (view->ndim != 1) {
        PyBuffer_Release(view);
        PyErr_Format(PyExc_ValueError, "%s must be a contiguous bytes-like object.", name);
        return -1;
    }
    return 0;
}

static PyObject *chipcoin_backend_info(PyObject *self, PyObject *Py_UNUSED(args))
{
    (void)self;
    return Py_BuildValue(
        "{s:s,s:s,s:s,s:i,s:i,s:i,s:i}",
        "backend", "mldsa-native",
        "upstream_commit", "9b0ee84f4cf399043eca59eca4e5f8531ca1d61b",
        "scheme", "ML-DSA-44",
        "seed_size", CHIPCOIN_MLDSA44_SEED_SIZE,
        "public_key_size", MLDSA44_PUBLICKEYBYTES,
        "secret_key_size", MLDSA44_SECRETKEYBYTES,
        "signature_size", MLDSA44_BYTES);
}

static PyObject *chipcoin_derive_keypair(PyObject *self, PyObject *args)
{
    PyObject *seed_obj;
    Py_buffer seed = {0};
    uint8_t pk[MLDSA44_PUBLICKEYBYTES];
    uint8_t sk[MLDSA44_SECRETKEYBYTES];
    int rc;
    PyObject *result = NULL;

    (void)self;
    if (!PyArg_ParseTuple(args, "O", &seed_obj)) {
        return NULL;
    }
    if (parse_bytes_arg(seed_obj, "seed", &seed) != 0) {
        return NULL;
    }
    if (seed.len != CHIPCOIN_MLDSA44_SEED_SIZE) {
        PyBuffer_Release(&seed);
        return raise_value_error("ML-DSA-44 seed must be exactly 32 bytes.");
    }

    rc = CHIPCOIN_MLDSA44_keypair_internal(pk, sk, (const uint8_t *)seed.buf);
    PyBuffer_Release(&seed);
    if (rc != 0) {
        return raise_runtime_error("ML-DSA-44 key derivation failed.");
    }

    result = Py_BuildValue("y#y#", sk, (Py_ssize_t)sizeof(sk), pk, (Py_ssize_t)sizeof(pk));
    memset(sk, 0, sizeof(sk));
    return result;
}

static PyObject *chipcoin_sign(PyObject *self, PyObject *args)
{
    PyObject *seed_obj;
    PyObject *digest_obj;
    Py_buffer seed = {0};
    Py_buffer digest = {0};
    uint8_t pk[MLDSA44_PUBLICKEYBYTES];
    uint8_t sk[MLDSA44_SECRETKEYBYTES];
    uint8_t sig[MLDSA44_BYTES];
    const uint8_t deterministic_rnd[CHIPCOIN_MLDSA44_SEED_SIZE] = {0};
    size_t siglen = 0;
    int rc;
    PyObject *result = NULL;

    (void)self;
    if (!PyArg_ParseTuple(args, "OO", &seed_obj, &digest_obj)) {
        return NULL;
    }
    if (parse_bytes_arg(seed_obj, "seed", &seed) != 0) {
        return NULL;
    }
    if (parse_bytes_arg(digest_obj, "digest", &digest) != 0) {
        PyBuffer_Release(&seed);
        return NULL;
    }
    if (seed.len != CHIPCOIN_MLDSA44_SEED_SIZE) {
        PyBuffer_Release(&seed);
        PyBuffer_Release(&digest);
        return raise_value_error("ML-DSA-44 seed must be exactly 32 bytes.");
    }
    if (digest.len != CHIPCOIN_MLDSA44_DIGEST_SIZE) {
        PyBuffer_Release(&seed);
        PyBuffer_Release(&digest);
        return raise_value_error("Transaction signature digest must be exactly 32 bytes.");
    }

    rc = CHIPCOIN_MLDSA44_keypair_internal(pk, sk, (const uint8_t *)seed.buf);
    PyBuffer_Release(&seed);
    if (rc != 0) {
        PyBuffer_Release(&digest);
        memset(sk, 0, sizeof(sk));
        return raise_runtime_error("ML-DSA-44 key derivation failed.");
    }
    rc = CHIPCOIN_MLDSA44_signature_internal(
        sig, &siglen, (const uint8_t *)digest.buf, (size_t)digest.len,
        NULL, 0, deterministic_rnd, sk, 0);
    PyBuffer_Release(&digest);
    memset(sk, 0, sizeof(sk));
    if (rc != 0 || siglen != MLDSA44_BYTES) {
        return raise_runtime_error("ML-DSA-44 signing failed.");
    }

    result = PyBytes_FromStringAndSize((const char *)sig, (Py_ssize_t)siglen);
    memset(sig, 0, sizeof(sig));
    return result;
}

static PyObject *chipcoin_verify(PyObject *self, PyObject *args)
{
    PyObject *public_key_obj;
    PyObject *digest_obj;
    PyObject *signature_obj;
    Py_buffer public_key = {0};
    Py_buffer digest = {0};
    Py_buffer signature = {0};
    int rc;

    (void)self;
    if (!PyArg_ParseTuple(args, "OOO", &public_key_obj, &digest_obj, &signature_obj)) {
        return NULL;
    }
    if (parse_bytes_arg(public_key_obj, "public_key", &public_key) != 0) {
        return NULL;
    }
    if (parse_bytes_arg(digest_obj, "digest", &digest) != 0) {
        PyBuffer_Release(&public_key);
        return NULL;
    }
    if (parse_bytes_arg(signature_obj, "signature", &signature) != 0) {
        PyBuffer_Release(&public_key);
        PyBuffer_Release(&digest);
        return NULL;
    }

    if (public_key.len != MLDSA44_PUBLICKEYBYTES ||
        digest.len != CHIPCOIN_MLDSA44_DIGEST_SIZE ||
        signature.len != MLDSA44_BYTES) {
        PyBuffer_Release(&public_key);
        PyBuffer_Release(&digest);
        PyBuffer_Release(&signature);
        Py_RETURN_FALSE;
    }

    rc = CHIPCOIN_MLDSA44_verify_internal(
        (const uint8_t *)signature.buf, (size_t)signature.len,
        (const uint8_t *)digest.buf, (size_t)digest.len, NULL, 0,
        (const uint8_t *)public_key.buf, 0);
    PyBuffer_Release(&public_key);
    PyBuffer_Release(&digest);
    PyBuffer_Release(&signature);
    if (rc == 0) {
        Py_RETURN_TRUE;
    }
    Py_RETURN_FALSE;
}

static PyMethodDef methods[] = {
    {"backend_info", chipcoin_backend_info, METH_NOARGS, "Return pinned ML-DSA backend metadata."},
    {"derive_keypair", chipcoin_derive_keypair, METH_VARARGS, "Derive ML-DSA-44 keypair from a 32-byte seed."},
    {"sign", chipcoin_sign, METH_VARARGS, "Deterministically sign a 32-byte digest with ML-DSA-44."},
    {"verify", chipcoin_verify, METH_VARARGS, "Verify an ML-DSA-44 signature over a 32-byte digest."},
    {NULL, NULL, 0, NULL},
};

static struct PyModuleDef moduledef = {
    PyModuleDef_HEAD_INIT,
    "_mldsa_native",
    "Vendored mldsa-native ML-DSA-44 backend.",
    -1,
    methods,
};

PyMODINIT_FUNC PyInit__mldsa_native(void)
{
    if (MLDSA44_PUBLICKEYBYTES != 1312 || MLDSA44_BYTES != 2420 ||
        MLDSA44_SECRETKEYBYTES != 2560) {
        PyErr_SetString(PyExc_ImportError, "Unexpected ML-DSA-44 constants.");
        return NULL;
    }
    if (api_guard_keypair == NULL || api_guard_signature == NULL || api_guard_verify == NULL) {
        PyErr_SetString(PyExc_ImportError, "mldsa-native API guard failed.");
        return NULL;
    }
    return PyModule_Create(&moduledef);
}
